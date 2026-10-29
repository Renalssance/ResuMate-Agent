import { buildAuthHeaders } from './authToken'
import { parseSseStream } from './sseParser'

export type RunStatus = 'queued' | 'running' | 'waiting_input' | 'waiting_approval' | 'succeeded' | 'failed' | 'cancelled'
export interface RunSnapshot {
  runId: string
  sessionId: string
  sessionInvalidated: boolean
  kind: string
  status: RunStatus
  input: Record<string, unknown>
  inputVersions: Record<string, string>
  attempt: number
  lastSeq: number
  errorCode: string | null
  cancelRequested: boolean
  outputRefs: unknown[]
  result?: Record<string, unknown> | null
  actions: { actionId: string; kind: 'input' | 'approval'; payload: Record<string, unknown>; revision: number }[]
}
export interface RunEvent {
  runId: string
  seq: number
  createdAt: string
  type: string
  payload: Record<string, unknown>
}
export class RunStreamError extends Error {
  constructor(public status: number, public code: string, message: string, public retryAfterMs?: number) {
    super(message)
    this.name = 'RunStreamError'
  }
}
export interface RunSubscriptionOptions {
  runId: string
  after?: number
  onEvent: (event: RunEvent) => void
  onSnapshot?: (snapshot: RunSnapshot) => void
  onReset?: (snapshot: RunSnapshot) => void
  onConnected?: (snapshot: RunSnapshot) => void
  onError?: (error: Error) => void
  signal?: AbortSignal
}
export interface RunSubscription { close: () => void; done: Promise<void> }
const retryDelays = [1000, 2000, 4000, 8000, 15000]
const terminalStatuses = new Set(['succeeded', 'failed', 'cancelled'])
const resetStream = Symbol('reset stream')
const terminalStream = Symbol('terminal stream')

function waitForRetry(delay: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.resolve()
  return new Promise((resolve) => {
    const finish = () => {
      clearTimeout(timer)
      signal.removeEventListener('abort', finish)
      resolve()
    }
    const timer = setTimeout(finish, delay)
    signal.addEventListener('abort', finish, { once: true })
  })
}

/** Read the snapshot, then replay from `after`. `close` only disconnects the viewer. */
export function subscribeRun(options: RunSubscriptionOptions): RunSubscription {
  const controller = new AbortController()
  const { signal } = controller
  let transport: AbortController | undefined
  const close = () => { controller.abort(); transport?.abort() }
  const offline = () => transport?.abort()
  window.addEventListener('offline', offline)
  if (options.signal?.aborted) close()
  else options.signal?.addEventListener('abort', close, { once: true })

  const url = `/api/agent/runs/${encodeURIComponent(options.runId)}`
  let cursor = options.after ?? 0
  let snapshot: RunSnapshot | undefined
  let resetting = false
  let retry = 0

  async function get(endpoint: string, accept: string): Promise<Response> {
    const response = await fetch(endpoint, { signal: transport!.signal, headers: { ...buildAuthHeaders(), Accept: accept } })
    if (response.ok) return response
    const body = await response.json().catch(() => ({}))
    const retryAfter = response.headers.get('Retry-After')
    let retryAfterMs: number | undefined
    if (response.status === 429 && retryAfter) {
      const seconds = Number(retryAfter)
      const delay = Number.isFinite(seconds) ? seconds * 1000 : Date.parse(retryAfter) - Date.now()
      if (Number.isFinite(delay)) retryAfterMs = Math.max(0, delay)
    }
    throw new RunStreamError(response.status, body.code || 'request_failed', body.message || `请求失败 (${response.status})`, retryAfterMs)
  }

  async function consume(): Promise<void> {
    while (!signal.aborted) {
      let retryAfterMs: number | undefined
      transport = new AbortController()
      try {
        // A retry may have completed while disconnected; refresh the replay boundary.
        const initialSnapshot = !snapshot
        snapshot = await (await get(url, 'application/json')).json() as RunSnapshot
        if (signal.aborted) return
        if (resetting) {
          cursor = snapshot.lastSeq
          options.onReset?.(snapshot)
        } else if (initialSnapshot) {
          options.onSnapshot?.(snapshot)
        }
        resetting = false
        if (signal.aborted) return
        const response = await get(`${url}/events?after=${cursor}`, 'text/event-stream')
        if (signal.aborted) return
        options.onConnected?.(snapshot)
        await parseSseStream(response, (frame) => {
          if (frame.event === 'reset') throw resetStream
          if (frame.event !== 'run.event') return
          const event = JSON.parse(frame.data) as RunEvent
          if (event.seq <= cursor) return
          if (event.seq !== cursor + 1) throw resetStream
          cursor = event.seq
          retry = 0
          options.onEvent(event)
          // A previous failed attempt can be followed by retry events in the same Run.
          if (event.type === 'run.status' && terminalStatuses.has(String(event.payload.status)) && cursor >= snapshot!.lastSeq) {
            throw terminalStream
          }
        }, transport.signal)
        if (signal.aborted || (terminalStatuses.has(snapshot.status) && cursor >= snapshot.lastSeq)) return
        options.onError?.(new Error('实时连接已中断，正在重新连接'))
      } catch (error) {
        if (signal.aborted || error === terminalStream) return
        if (error === resetStream || (error instanceof RunStreamError && error.status === 409 && error.code === 'cursor_reset')) {
          resetting = true
          continue
        }
        options.onError?.(error instanceof Error ? error : new Error(String(error)))
        if (error instanceof RunStreamError) {
          if (error.status >= 400 && error.status < 500 && error.status !== 429) return
          retryAfterMs = error.retryAfterMs
        }
      }
      await waitForRetry(retryAfterMs ?? retryDelays[Math.min(retry, retryDelays.length - 1)], signal)
      retry += 1
    }
  }

  const done = consume().finally(() => {
    options.signal?.removeEventListener('abort', close)
    window.removeEventListener('offline', offline)
  })
  return { close, done }
}

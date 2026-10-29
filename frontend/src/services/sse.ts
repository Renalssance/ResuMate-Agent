import type { SseProgressEvent } from '../types/task'
import { buildAuthHeaders } from './authToken'
import { parseSseStream } from './sseParser'

interface TaskCallbacks {
  onMessage: (event: SseProgressEvent) => void
  onError?: (error: Error) => void
  onReconnect?: () => void
  onClose?: () => void
}

export interface TaskConnection { close: () => void }
const activeConnections = new Map<string, Set<TaskConnection>>()
const retryDelays = [1000, 2000, 4000, 8000, 15000]
const resetCursor = Symbol('reset task cursor')

class TaskStreamError extends Error {
  constructor(public status: number, public code: string, message: string, public retryAfter?: number) { super(message) }
}

function waitForRetry(milliseconds: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.resolve()
  return new Promise(resolve => {
    const finish = () => { clearTimeout(timer); signal.removeEventListener('abort', finish); resolve() }
    const timer = setTimeout(finish, milliseconds)
    signal.addEventListener('abort', finish, { once: true })
  })
}

/** One durable stream. Result waiters own this connection independently of the page. */
export function openTaskProgress(taskId: string, callbacks: TaskCallbacks): TaskConnection {
  const controller = new AbortController()
  let closed = false, cursor = 0, retry = 0
  let transport: AbortController | undefined
  const offline = () => transport?.abort()
  window.addEventListener('offline', offline)
  const connection: TaskConnection = {
    close() {
      if (closed) return
      closed = true
      controller.abort()
      transport?.abort()
      window.removeEventListener('offline', offline)
      callbacks.onClose?.()
    },
  }
  void (async () => {
    while (!closed) {
      let retryAfter: number | undefined
      transport = new AbortController()
      try {
        const suffix = cursor ? `?after=${cursor}` : ''
        const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/events${suffix}`, {
          headers: { ...buildAuthHeaders(), Accept: 'text/event-stream' }, signal: transport.signal,
        })
        if (closed) return
        if (!response.ok) {
          const body = await response.json().catch(() => ({}))
          const delay = Number(response.headers.get('Retry-After'))
          throw new TaskStreamError(response.status, body.code || '', body.message || body.detail || `进度请求失败 (${response.status})`, response.status === 429 && delay > 0 ? delay * 1000 : undefined)
        }
        await parseSseStream(response, frame => {
          if (frame.event === 'reset') throw resetCursor
          const event = JSON.parse(frame.data) as SseProgressEvent
          if (frame.id !== undefined) {
            const sequence = Number(frame.id)
            if (sequence <= cursor) return
            // Legacy progress is a filtered projection; gaps are intentional.
            cursor = sequence
          }
          retry = 0
          callbacks.onMessage(event)
          if (event.status === 'success' || event.status === 'failed') connection.close()
        }, transport.signal)
      } catch (error) {
        if (closed) return
        if (error === resetCursor || (error instanceof TaskStreamError && error.status === 409 && error.code === 'cursor_reset')) {
          cursor = 0
          continue
        }
        if (error instanceof SyntaxError || (error instanceof TaskStreamError && error.status >= 400 && error.status < 500 && error.status !== 429)) {
          callbacks.onError?.(error)
          connection.close()
          return
        }
        if (error instanceof TaskStreamError) retryAfter = error.retryAfter
      }
      if (closed) return
      callbacks.onReconnect?.()
      await waitForRetry(retryAfter ?? retryDelays[Math.min(retry, retryDelays.length - 1)]!, controller.signal)
      retry++
    }
  })()
  return connection
}

export function subscribeTaskProgress(taskId: string, callbacks: TaskCallbacks): TaskConnection {
  const connections = activeConnections.get(taskId) || new Set<TaskConnection>()
  const connection = openTaskProgress(taskId, {
    ...callbacks,
    onClose() {
      connections.delete(connection)
      if (!connections.size) activeConnections.delete(taskId)
      callbacks.onClose?.()
    },
  })
  connections.add(connection)
  activeConnections.set(taskId, connections)
  return connection
}

export function closeTaskProgress(taskId: string) {
  for (const connection of activeConnections.get(taskId) || []) connection.close()
}

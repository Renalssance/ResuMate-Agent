import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { subscribeRun, type RunEvent, type RunSnapshot, type RunStreamError } from './agentStream'

const encoder = new TextEncoder()
const runId = 'run-1'

function snapshot(overrides: Partial<RunSnapshot> = {}): RunSnapshot {
  return {
    runId, sessionId: 'session-1', kind: 'tailoring', status: 'running',
    input: { jdId: 1, resumeId: 2 }, inputVersions: { resume: 'v1', jd: 'v1' },
    attempt: 1, lastSeq: 0, errorCode: null, cancelRequested: false, outputRefs: [], actions: [],
    ...overrides,
  }
}

function event(seq: number, type = 'assistant.delta', payload: Record<string, unknown> = { text: '你好' }) {
  return { runId, seq, createdAt: '2026-10-29T12:00:00Z', type, payload }
}

function frame(value: ReturnType<typeof event>) {
  return `event: run.event\nid: ${value.seq}\ndata: ${JSON.stringify(value)}\n\n`
}

function stream(text: string, open = false, cancel?: () => void) {
  return new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(text))
      if (!open) controller.close()
    },
    cancel,
  }), { headers: { 'Content-Type': 'text/event-stream' } })
}

function terminal(seq: number, status = 'succeeded') {
  return frame(event(seq, 'run.status', { status, error_code: null }))
}

function respond(...responses: Response[]) {
  const fetcher = vi.fn()
  for (const response of responses) fetcher.mockResolvedValueOnce(response)
  vi.stubGlobal('fetch', fetcher)
  return fetcher
}

beforeEach(() => {
  vi.useFakeTimers()
  window.localStorage.setItem('accessToken', 'token-123')
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  window.localStorage.clear()
})

describe('subscribeRun', () => {
  it('authenticates snapshot and stream and replays terminal snapshot history before closing', async () => {
    const fetcher = respond(Response.json(snapshot({ status: 'succeeded', lastSeq: 2 })), stream(frame(event(1)) + terminal(2)))
    const received: string[] = []
    const subscription = subscribeRun({ runId, onSnapshot: (value) => received.push(value.status), onEvent: (value) => received.push(String(value.seq)) })
    await subscription.done
    expect(received).toEqual(['succeeded', '1', '2'])
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual(['/api/agent/runs/run-1', '/api/agent/runs/run-1/events?after=0'])
    for (const [, options] of fetcher.mock.calls) expect(new Headers(options.headers).get('Authorization')).toBe('Bearer token-123')
    await vi.advanceTimersByTimeAsync(20000)
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('resumes after the last complete event and deduplicates replayed events', async () => {
    const fetcher = respond(
      Response.json(snapshot({ lastSeq: 1 })),
      stream(frame(event(1)) + 'event: run.event\nid: 2\ndata: {"runId":'),
      Response.json(snapshot({ status: 'succeeded', lastSeq: 3 })),
      stream(frame(event(1)) + frame(event(2)) + terminal(3)),
    )
    const received: number[] = []
    const subscription = subscribeRun({ runId, onEvent: (value) => received.push(value.seq) })
    await vi.advanceTimersByTimeAsync(0)
    expect(received).toEqual([1])
    await vi.advanceTimersByTimeAsync(999)
    expect(fetcher).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(1)
    await subscription.done
    expect(received).toEqual([1, 2, 3])
    expect(fetcher.mock.calls[3][0]).toBe('/api/agent/runs/run-1/events?after=1')
  })

  it('uses the caller cursor even when the snapshot includes newer events', async () => {
    const fetcher = respond(Response.json(snapshot({ lastSeq: 5 })), stream(frame(event(4)) + terminal(5)))
    const received: number[] = []
    await subscribeRun({ runId, after: 3, onEvent: (value) => received.push(value.seq) }).done
    expect(received).toEqual([4, 5])
    expect(fetcher.mock.calls[1][0]).toBe('/api/agent/runs/run-1/events?after=3')
  })

  it('does not stop replay at a failed attempt that was subsequently retried', async () => {
    respond(Response.json(snapshot({ lastSeq: 3 })), stream(terminal(1, 'failed') + frame(event(2, 'run.status', { status: 'queued' })) + frame(event(3, 'run.status', { status: 'running' })) + terminal(4)))
    const received: number[] = []
    await subscribeRun({ runId, onEvent: (value) => received.push(value.seq) }).done
    expect(received).toEqual([1, 2, 3, 4])
  })

  it('refreshes the replay boundary when a disconnected Run fails and is retried', async () => {
    let snapshots = 0
    let streams = 0
    const fetcher = vi.fn(async (url: string) => {
      if (!url.includes('/events?')) {
        snapshots += 1
        return Response.json(snapshots === 1 ? snapshot({ lastSeq: 1 }) : snapshot({ status: 'succeeded', lastSeq: 5, attempt: 2 }))
      }
      streams += 1
      return streams === 1 ? stream(frame(event(1, 'run.status', { status: 'running' }))) : stream(
        terminal(2, 'failed') + frame(event(3, 'run.status', { status: 'queued' }))
        + frame(event(4, 'run.status', { status: 'running' })) + terminal(5),
      )
    })
    vi.stubGlobal('fetch', fetcher)
    const received: number[] = []
    const initialSnapshots: number[] = []
    const resets: RunSnapshot[] = []
    const subscription = subscribeRun({
      runId, onEvent: (value) => received.push(value.seq),
      onSnapshot: (value) => initialSnapshots.push(value.lastSeq), onReset: (value) => resets.push(value),
    })
    await vi.advanceTimersByTimeAsync(1000)
    await subscription.done
    expect(received).toEqual([1, 2, 3, 4, 5])
    expect(initialSnapshots).toEqual([1])
    expect(resets).toEqual([])
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      '/api/agent/runs/run-1', '/api/agent/runs/run-1/events?after=0',
      '/api/agent/runs/run-1', '/api/agent/runs/run-1/events?after=1',
    ])
  })

  it('stops at EOF when the caller already consumed a terminal snapshot', async () => {
    const fetcher = respond(Response.json(snapshot({ status: 'cancelled', lastSeq: 3 })), stream(''))
    await subscribeRun({ runId, after: 3, onEvent: () => {} }).done
    await vi.advanceTimersByTimeAsync(20000)
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it.each([401, 403, 404])('stops after HTTP %s on the event connection', async (status) => {
    const fetcher = respond(Response.json(snapshot()), Response.json({ code: 'denied', message: '拒绝访问' }, { status }))
    const errors: RunStreamError[] = []
    await subscribeRun({ runId, onEvent: () => {}, onError: (error) => errors.push(error as RunStreamError) }).done
    await vi.advanceTimersByTimeAsync(30000)
    expect(errors.map((error) => [error.status, error.code])).toEqual([[status, 'denied']])
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('stops on snapshot authorization failure before opening the stream', async () => {
    const fetcher = respond(Response.json({ code: 'unauthorized', message: '请登录' }, { status: 401 }))
    const errors: Error[] = []
    await subscribeRun({ runId, onEvent: () => {}, onError: (error) => errors.push(error) }).done
    expect(errors).toHaveLength(1)
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('closes only the subscription when aborted while reading', async () => {
    const abort = new AbortController()
    let cancelled = false
    const fetcher = respond(Response.json(snapshot()), stream(frame(event(1)), true, () => { cancelled = true }))
    const received: RunEvent[] = []
    const errors: Error[] = []
    const subscription = subscribeRun({ runId, signal: abort.signal, onEvent: (value) => received.push(value), onError: (error) => errors.push(error) })
    await vi.advanceTimersByTimeAsync(0)
    abort.abort()
    await subscription.done
    await vi.advanceTimersByTimeAsync(30000)
    expect(received.map((value) => value.seq)).toEqual([1])
    expect(cancelled).toBe(true)
    expect(errors).toEqual([])
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual(['/api/agent/runs/run-1', '/api/agent/runs/run-1/events?after=0'])
  })

  it('does not connect when the subscription signal is already aborted', async () => {
    const abort = new AbortController()
    abort.abort()
    const fetcher = respond()
    await subscribeRun({ runId, signal: abort.signal, onEvent: () => {} }).done
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('backs off failed reconnects at 1, 2, 4, 8 and at most 15 seconds', async () => {
    const fetcher = respond(Response.json(snapshot()))
    fetcher.mockRejectedValue(new TypeError('network disconnected'))
    const subscription = subscribeRun({ runId, onEvent: () => {} })
    await vi.advanceTimersByTimeAsync(0)
    let calls = 2
    for (const delay of [1000, 2000, 4000, 8000, 15000, 15000]) {
      await vi.advanceTimersByTimeAsync(delay - 1)
      expect(fetcher).toHaveBeenCalledTimes(calls)
      await vi.advanceTimersByTimeAsync(1)
      expect(fetcher).toHaveBeenCalledTimes(++calls)
    }
    subscription.close()
    await subscription.done
    await vi.advanceTimersByTimeAsync(30000)
    expect(fetcher).toHaveBeenCalledTimes(calls)
  })

  it.each(['seconds', 'date'])('honors Retry-After as %s on 429', async (format) => {
    vi.setSystemTime(new Date('2026-10-29T12:00:00Z'))
    const retryAfter = format === 'seconds' ? '3' : 'Thu, 29 Oct 2026 12:00:03 GMT'
    const fetcher = respond(Response.json(snapshot()), Response.json({ code: 'rate_limited' }, { status: 429, headers: { 'Retry-After': retryAfter } }), Response.json(snapshot({ status: 'succeeded', lastSeq: 1 })), stream(terminal(1)))
    const subscription = subscribeRun({ runId, onEvent: () => {} })
    await vi.advanceTimersByTimeAsync(2999)
    expect(fetcher).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(1)
    await subscription.done
    expect(fetcher).toHaveBeenCalledTimes(4)
  })

  it.each(['http', 'control', 'gap'])('refreshes the snapshot on %s cursor reset and resumes from its lastSeq', async (reason) => {
    const first = reason === 'http'
      ? Response.json({ code: 'cursor_reset', message: '游标已过期' }, { status: 409 })
      : stream(frame(event(1)) + (reason === 'control' ? 'event: reset\ndata: {"code":"cursor_reset"}\n\n' : frame(event(3))))
    const fetcher = respond(Response.json(snapshot({ lastSeq: 1 })), first, Response.json(snapshot({ lastSeq: 5 })), stream(terminal(6)))
    const received: number[] = []
    const resets: number[] = []
    const subscription = subscribeRun({ runId, onEvent: (value) => received.push(value.seq), onReset: (value) => resets.push(value.lastSeq) })
    await subscription.done
    expect(resets).toEqual([5])
    expect(received).toEqual(reason === 'http' ? [6] : [1, 6])
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      '/api/agent/runs/run-1', '/api/agent/runs/run-1/events?after=0', '/api/agent/runs/run-1', '/api/agent/runs/run-1/events?after=5',
    ])
  })
})

it('notifies the workspace when an idle stream reconnects with an authoritative snapshot', async () => {
  respond(Response.json(snapshot()), stream(''), Response.json(snapshot({ status: 'waiting_input', lastSeq: 2 })), stream('', true))
  const connected = vi.fn()
  const subscription = subscribeRun({ runId, onEvent: () => {}, onConnected: connected })
  await vi.advanceTimersByTimeAsync(0)
  await vi.advanceTimersByTimeAsync(1000)
  expect(connected.mock.calls.map(([value]) => value.status)).toEqual(['running', 'waiting_input'])
  subscription.close(); await subscription.done
})

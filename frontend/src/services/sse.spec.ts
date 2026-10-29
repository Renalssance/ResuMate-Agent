import { afterEach, expect, it, vi } from 'vitest'
import { closeTaskProgress, subscribeTaskProgress } from './sse'
import { waitForTaskResult } from './taskResult'

function eventStream() {
  let writer!: ReadableStreamDefaultController<Uint8Array>
  const cancelled = vi.fn()
  const body = new ReadableStream<Uint8Array>({ start(controller) { writer = controller }, cancel: cancelled })
  return {
    response: new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }),
    cancelled,
    end() { writer.close() },
    emit(status: 'running' | 'success', id?: number) {
      writer.enqueue(new TextEncoder().encode(`${id === undefined ? '' : `id: ${id}\n`}data: ${JSON.stringify({ taskId: 'same-task', status, data: { value: 7 } })}\n\n`))
    },
  }
}

afterEach(() => {
  closeTaskProgress('same-task')
  vi.useRealTimers()
  vi.unstubAllGlobals()
  window.localStorage.clear()
})

it('sends bearer credentials and keeps UI connections independent from the result waiter', async () => {
  window.localStorage.setItem('accessToken', 'current-token')
  const first = eventStream(), second = eventStream(), resultStream = eventStream()
  const fetch = vi.fn().mockResolvedValueOnce(first.response).mockResolvedValueOnce(second.response).mockResolvedValueOnce(resultStream.response)
  vi.stubGlobal('fetch', fetch)
  vi.stubGlobal('EventSource', class { close() {} })
  const firstClosed = vi.fn(), secondMessage = vi.fn()
  const firstConnection = subscribeTaskProgress('same-task', { onMessage() {}, onClose: firstClosed })
  subscribeTaskProgress('same-task', { onMessage: secondMessage })
  const result = waitForTaskResult('same-task', data => data.value)
  await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(3))
  for (const [url, options] of fetch.mock.calls) {
    expect(url).toBe('/api/tasks/same-task/events')
    expect(options.headers.Authorization).toBe('Bearer current-token')
  }
  expect(firstClosed).not.toHaveBeenCalled()
  firstConnection.close()
  firstConnection.close()
  expect(firstClosed).toHaveBeenCalledTimes(1)
  second.emit('running')
  await vi.waitFor(() => expect(secondMessage).toHaveBeenCalledTimes(1))
  closeTaskProgress('same-task')
  expect(resultStream.cancelled).not.toHaveBeenCalled()
  resultStream.emit('success')
  await expect(result).resolves.toBe(7)
  await vi.waitFor(() => expect(resultStream.cancelled).toHaveBeenCalledTimes(1))
})

it('rejects HTTP authentication failures and closes progress exactly once', async () => {
  const fetch = vi.fn().mockImplementation(async () => new Response('{}', { status: 401 }))
  vi.stubGlobal('fetch', fetch)
  const error = vi.fn(), close = vi.fn()
  const connection = subscribeTaskProgress('same-task', { onMessage() {}, onError: error, onClose: close })
  await vi.waitFor(() => expect(error).toHaveBeenCalledTimes(1))
  expect(error.mock.calls[0]?.[0].message).toContain('401')
  expect(close).toHaveBeenCalledTimes(1)
  connection.close()
  expect(close).toHaveBeenCalledTimes(1)
  await expect(waitForTaskResult('same-task', data => data)).rejects.toThrow('401')
})

it('reports malformed event data and closes its subscription', async () => {
  const fetch = vi.fn().mockImplementation(async () => new Response('data: not-json\n\n'))
  vi.stubGlobal('fetch', fetch)
  const error = vi.fn(), close = vi.fn()
  subscribeTaskProgress('same-task', { onMessage() {}, onError: error, onClose: close })
  await vi.waitFor(() => expect(error).toHaveBeenCalledTimes(1))
  expect(close).toHaveBeenCalledTimes(1)
  await expect(waitForTaskResult('same-task', data => data)).rejects.toThrow()
})


it('reconnects from the last event ID, allows filtered sequence gaps and ignores duplicate replay', async () => {
  vi.useFakeTimers()
  const first = eventStream(), second = eventStream()
  const fetch = vi.fn().mockResolvedValueOnce(first.response).mockResolvedValueOnce(second.response)
  vi.stubGlobal('fetch', fetch)
  const messages = vi.fn(), error = vi.fn(), close = vi.fn()
  subscribeTaskProgress('same-task', { onMessage: messages, onError: error, onClose: close })
  first.emit('running', 4)
  first.end()
  await vi.advanceTimersByTimeAsync(0)
  expect(messages).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(1000)
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(fetch.mock.calls[1]?.[0]).toBe('/api/tasks/same-task/events?after=4')
  second.emit('running', 4)
  second.emit('success', 9)
  await vi.advanceTimersByTimeAsync(0)
  expect(messages).toHaveBeenCalledTimes(2)
  expect(error).not.toHaveBeenCalled()
  expect(close).toHaveBeenCalledTimes(1)
})

it('keeps the result pending across a disconnect and obtains the durable final response', async () => {
  vi.useFakeTimers()
  const first = eventStream(), second = eventStream()
  const fetch = vi.fn().mockResolvedValueOnce(first.response).mockResolvedValueOnce(second.response)
  vi.stubGlobal('fetch', fetch)
  const result = waitForTaskResult('same-task', data => data.value)
  const settled = vi.fn()
  const observed = result.then(value => { settled(value); return value }, error => { settled(error); return error })
  first.emit('running', 2)
  first.end()
  await vi.advanceTimersByTimeAsync(0)
  expect(settled).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(1000)
  expect(fetch.mock.calls[1]?.[0]).toBe('/api/tasks/same-task/events?after=2')
  second.emit('success', 8)
  await expect(observed).resolves.toBe(7)
})

it('cancels a pending reconnect when the viewer closes', async () => {
  vi.useFakeTimers()
  const stream = eventStream()
  const fetch = vi.fn().mockResolvedValue(stream.response)
  vi.stubGlobal('fetch', fetch)
  const connection = subscribeTaskProgress('same-task', { onMessage() {} })
  stream.end()
  await vi.advanceTimersByTimeAsync(0)
  connection.close()
  await vi.advanceTimersByTimeAsync(16000)
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('closes a stalled transport on the browser offline event and resumes from the durable cursor', async () => {
  vi.useFakeTimers()
  const first = eventStream(), second = eventStream()
  const fetch = vi.fn().mockResolvedValueOnce(first.response).mockResolvedValueOnce(second.response)
  vi.stubGlobal('fetch', fetch)
  const reconnect = vi.fn(), error = vi.fn(), messages = vi.fn()
  const connection = subscribeTaskProgress('same-task', { onMessage: messages, onReconnect: reconnect, onError: error })
  first.emit('running', 4)
  await vi.advanceTimersByTimeAsync(0)
  window.dispatchEvent(new Event('offline'))
  await vi.advanceTimersByTimeAsync(0)
  expect(first.cancelled).toHaveBeenCalledTimes(1)
  expect(reconnect).toHaveBeenCalledTimes(1)
  expect(error).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(1000)
  expect(fetch.mock.calls[1]?.[0]).toBe('/api/tasks/same-task/events?after=4')
  second.emit('success', 9)
  await vi.advanceTimersByTimeAsync(0)
  expect(messages).toHaveBeenCalledTimes(2)
  connection.close()
  window.dispatchEvent(new Event('offline'))
  expect(reconnect).toHaveBeenCalledTimes(1)
})

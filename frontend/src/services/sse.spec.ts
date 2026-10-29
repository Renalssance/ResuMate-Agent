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
    emit(status: 'running' | 'success') {
      writer.enqueue(new TextEncoder().encode(`data: ${JSON.stringify({ taskId: 'same-task', status, data: { value: 7 } })}\n\n`))
    },
  }
}

afterEach(() => {
  closeTaskProgress('same-task')
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

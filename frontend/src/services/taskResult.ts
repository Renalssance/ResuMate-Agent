import type { SseProgressEvent } from '../types/task'
import { buildAuthHeaders } from './authToken'
import { parseSseStream } from './sseParser'

export interface AcceptedTask {
  taskId: string
}

// Keep this connection separate from the UI's progress subscription.
export async function waitForTaskResult<T>(taskId: string, select: (data: Record<string, unknown>) => T): Promise<T> {
  const controller = new AbortController()
  let completed = false
  let result: T | undefined
  try {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/events`, {
      headers: { ...buildAuthHeaders(), Accept: 'text/event-stream' },
      signal: controller.signal,
    })
    if (!response.ok) throw new Error(`Task result request failed (${response.status})`)
    await parseSseStream(response, (frame) => {
      const event = JSON.parse(frame.data) as SseProgressEvent
      if (event.status === 'failed') throw new Error(event.message)
      if (event.status === 'success') {
        result = select(event.data || {})
        completed = true
        controller.abort()
      }
    }, controller.signal)
    if (!completed) throw new Error('Task result connection closed')
    return result as T
  } finally {
    controller.abort()
  }
}

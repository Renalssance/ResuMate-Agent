import type { SseProgressEvent } from '../types/task'

export interface AcceptedTask {
  taskId: string
}

// Keep this connection separate from the UI's progress subscription.
export function waitForTaskResult<T>(taskId: string, select: (data: Record<string, unknown>) => T): Promise<T> {
  return new Promise((resolve, reject) => {
    const source = new EventSource(`/api/tasks/${encodeURIComponent(taskId)}/events`)
    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as SseProgressEvent
        if (event.status === 'failed') {
          source.close()
          reject(new Error(event.message))
        } else if (event.status === 'success') {
          source.close()
          resolve(select(event.data || {}))
        }
      } catch (error) {
        source.close()
        reject(error)
      }
    }
    source.onerror = () => {
      source.close()
      reject(new Error('Task result connection closed'))
    }
  })
}

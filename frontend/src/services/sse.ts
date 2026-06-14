import type { SseProgressEvent } from '../types/task'

interface TaskCallbacks {
  onMessage: (event: SseProgressEvent) => void
  onError?: (error: Error) => void
  onClose?: () => void
}

export interface TaskConnection {
  close: () => void
}

const activeConnections = new Map<string, TaskConnection>()

export function subscribeTaskProgress(taskId: string, callbacks: TaskCallbacks) {
  const existing = activeConnections.get(taskId)
  if (existing) existing.close()

  const source = new EventSource(`/api/tasks/${taskId}/events`)
  let terminalClose = false
  const connection = {
    close: () => {
      source.close()
      activeConnections.delete(taskId)
      callbacks.onClose?.()
    },
  }

  source.onmessage = (message) => {
    try {
      const event = JSON.parse(message.data) as SseProgressEvent
      callbacks.onMessage(event)
      if (event.status === 'success' || event.status === 'failed') {
        terminalClose = true
        connection.close()
      }
    } catch {
      callbacks.onError?.(new Error('SSE event parse failed'))
    }
  }

  source.onerror = () => {
    if (!terminalClose) callbacks.onError?.(new Error('SSE connection closed'))
    connection.close()
  }

  activeConnections.set(taskId, connection)
  return connection
}

export function closeTaskProgress(taskId: string) {
  activeConnections.get(taskId)?.close()
}

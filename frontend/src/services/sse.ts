import type { SseProgressEvent } from '../types/task'
import { buildAuthHeaders } from './authToken'
import { parseSseStream } from './sseParser'

interface TaskCallbacks {
  onMessage: (event: SseProgressEvent) => void
  onError?: (error: Error) => void
  onClose?: () => void
}

export interface TaskConnection {
  close: () => void
}

const activeConnections = new Map<string, Set<TaskConnection>>()

export function subscribeTaskProgress(taskId: string, callbacks: TaskCallbacks): TaskConnection {
  const controller = new AbortController()
  let closed = false
  const connections = activeConnections.get(taskId) || new Set<TaskConnection>()
  const connection = {
    close: () => {
      if (closed) return
      closed = true
      controller.abort()
      connections.delete(connection)
      if (!connections.size) activeConnections.delete(taskId)
      callbacks.onClose?.()
    },
  }
  connections.add(connection)
  activeConnections.set(taskId, connections)

  void (async () => {
    try {
      const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/events`, {
        headers: { ...buildAuthHeaders(), Accept: 'text/event-stream' },
        signal: controller.signal,
      })
      if (!response.ok) throw new Error(`SSE request failed (${response.status})`)
      await parseSseStream(response, (frame) => {
        const event = JSON.parse(frame.data) as SseProgressEvent
        callbacks.onMessage(event)
        if (event.status === 'success' || event.status === 'failed') connection.close()
      }, controller.signal)
      if (!closed) throw new Error('SSE connection closed')
    } catch (error) {
      if (!closed) callbacks.onError?.(error instanceof Error ? error : new Error(String(error)))
    } finally {
      connection.close()
    }
  })()
  return connection
}

export function closeTaskProgress(taskId: string) {
  for (const connection of activeConnections.get(taskId) || []) connection.close()
}

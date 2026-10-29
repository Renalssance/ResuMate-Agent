import { openTaskProgress } from './sse'

export interface AcceptedTask { taskId: string }

// Page navigation can close UI progress without cancelling the accepted task/result wait.
export function waitForTaskResult<T>(taskId: string, select: (data: Record<string, unknown>) => T): Promise<T> {
  return new Promise((resolve, reject) => {
    const connection = openTaskProgress(taskId, {
      onMessage(event) {
        if (event.status === 'failed') reject(new Error(event.message))
        if (event.status === 'success') {
          try { resolve(select(event.data || {})) }
          catch (error) { reject(error); connection.close() }
        }
      },
      onError: reject,
    })
  })
}

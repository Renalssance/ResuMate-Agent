import { expect, it, vi } from 'vitest'
import { createDocumentUploadQueue } from './useDocumentParseTasks'
import type { DocumentRecord } from '../types/document'

it.each(['upload', 'reparse'])('starts %s progress only after the server accepts the task', async (operation) => {
  let accept!: (taskId: string) => void
  let finish!: () => void
  const pending = new Promise<void>(resolve => { finish = resolve })
  const subscribe = vi.fn((_taskId: string) => ({ close() {} }))
  const queue = createDocumentUploadQueue({
    createTaskId: () => 'accepted-task',
    subscribe,
    upload: async (_type, _file, _taskId, _progress, onAccepted) => {
      accept = onAccepted!
      await pending
      return { documents: [] }
    },
    reparse: async (_documentId, _taskId, onAccepted) => { accept = onAccepted!; await pending },
  })
  const result = operation === 'upload'
    ? queue.enqueueFiles('resume', [new File(['resume'], 'resume.txt')])
    : queue.reparseDocument({ id: 'resume:1', filename: 'resume.txt', type: 'resume' } as DocumentRecord)
  expect(subscribe).not.toHaveBeenCalled()
  accept('accepted-task')
  expect(subscribe).toHaveBeenCalledOnce()
  expect(subscribe.mock.calls[0]?.[0]).toBe('accepted-task')
  finish()
  await result
  queue.closeAll()
})

it('does not open a late upload subscription after the view closes', async () => {
  let accept!: (taskId: string) => void
  let finish!: () => void
  const pending = new Promise<void>(resolve => { finish = resolve })
  const subscribe = vi.fn((_taskId: string) => ({ close() {} }))
  const queue = createDocumentUploadQueue({
    createTaskId: () => 'accepted-task', subscribe,
    upload: async (_type, _file, _taskId, _progress, onAccepted) => {
      accept = onAccepted!
      await pending
      return { documents: [] }
    },
  })
  const result = queue.enqueueFiles('resume', [new File(['resume'], 'resume.txt')])
  queue.closeAll()
  accept('accepted-task')
  expect(subscribe).not.toHaveBeenCalled()
  finish()
  await result
})

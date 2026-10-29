import { afterEach, expect, it, vi } from 'vitest'
import { createDocumentUploadQueue } from './useDocumentParseTasks'
import type { DocumentRecord } from '../types/document'
import { request } from '../services/request'
afterEach(() => localStorage.clear())

it.each(['upload', 'reparse'])('starts %s progress only after the server accepts the task', async (operation) => {
  let accept!: (taskId: string) => void
  let finish!: () => void
  const pending = new Promise<void>(resolve => { finish = resolve })
  const subscribe = vi.fn((_taskId: string) => ({ close() {} }))
  const queue = createDocumentUploadQueue({
    createTaskId: () => 'local-request-key',
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
  expect([...queue.tasks.keys()]).toEqual(['accepted-task'])
  expect(queue.tasks.get('accepted-task')?.taskId).toBe('accepted-task')
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

it('restores an accepted upload after closing and reopening the document page', async () => {
  localStorage.setItem('username', 'restore-user')
  let accept!: (taskId: string) => void
  let finish!: () => void
  const pending = new Promise<void>(resolve => { finish = resolve })
  const first = createDocumentUploadQueue({
    createTaskId: () => 'local-upload', subscribe: () => ({ close() {} }),
    upload: async (_type, _file, _taskId, _progress, onAccepted) => { accept = onAccepted!; await pending; return { documents: [] } },
  })
  const submitted = first.enqueueFiles('resume', [new File(['resume'], '很长的中文简历文件名.txt')])
  accept('persisted-upload')
  first.closeAll()
  const subscribe = vi.fn((_id: string, _callbacks: any) => ({ close() {} }))
  const restored = createDocumentUploadQueue({ subscribe })
  expect(restored.tasks.get('persisted-upload')?.filename).toBe('很长的中文简历文件名.txt')
  expect(subscribe.mock.calls[0]?.[0]).toBe('persisted-upload')
  subscribe.mock.calls[0]?.[1].onMessage({ taskId: 'persisted-upload', status: 'success', stage: 'completed', progress: 100, message: '完成' })
  restored.closeAll()
  const lastSubscribe = vi.fn(() => ({ close() {} }))
  const finished = createDocumentUploadQueue({ subscribe: lastSubscribe })
  expect(lastSubscribe).not.toHaveBeenCalled()
  finish(); await submitted; finished.closeAll(); localStorage.clear()
})


it.each(['page close', 'account change'])('stops unaccepted uploads after %s without cancelling accepted work', async reason => {
  localStorage.setItem('username', 'alice'); localStorage.setItem('accessToken', 'alice-token')
  const adapter = request.defaults.adapter
  const requests: { account: string; filename: string }[] = []
  let writer!: ReadableStreamDefaultController<Uint8Array>
  const acceptedStream = new Response(new ReadableStream<Uint8Array>({ start(value) { writer = value } }))
  const terminal = (id: string) => `id: 1\ndata: ${JSON.stringify({ taskId: id, stage: 'completed', status: 'success', data: { documents: [] } })}\n\n`
  request.defaults.adapter = async config => {
    requests.push({ account: String(config.headers.Authorization), filename: config.data.get('files').name })
    return { data: { taskId: `accepted-${requests.length}` }, status: 202, statusText: 'Accepted', headers: {}, config }
  }
  const fetcher = vi.fn(async (url: string) => url.includes('accepted-1') ? acceptedStream : new Response(terminal('accepted-2')))
  vi.stubGlobal('fetch', fetcher)
  const queue = createDocumentUploadQueue({ subscribe: () => ({ close() {} }) })
  try {
    const result = queue.enqueueFiles('resume', [new File(['a'], 'alice-first.pdf'), new File(['b'], 'alice-second.pdf')])
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1))
    if (reason === 'page close') queue.closeAll()
    localStorage.setItem('username', 'bob'); localStorage.setItem('accessToken', 'bob-token')
    writer.enqueue(new TextEncoder().encode(terminal('accepted-1')))
    expect(await result).toEqual([true, false])
    expect(requests).toEqual([{ account: 'Bearer alice-token', filename: 'alice-first.pdf' }])
  } finally {
    queue.closeAll(); request.defaults.adapter = adapter; vi.unstubAllGlobals()
  }
})

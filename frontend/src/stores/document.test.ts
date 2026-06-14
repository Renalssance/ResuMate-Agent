import { setActivePinia, createPinia } from 'pinia'
import { useDocumentStore } from './document'
import { createDocumentUploadQueue } from '../composables/useDocumentParseTasks'
import type { BackendDocumentParseResult } from '../api/documents'
import type { SseProgressEvent } from '../types/task'

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

const backendDoc = (id: string, parse_status = 'success'): BackendDocumentParseResult => ({
  id,
  type: 'resume',
  filename: `${id}.pdf`,
  size: 42,
  raw_text: 'Candidate text',
  parsed_content: {},
  vectorized: parse_status === 'success',
  local_stored: true,
  parse_status,
  created_at: '2026-06-14T00:00:00Z',
})

setActivePinia(createPinia())
const store = useDocumentStore()

store.upsertDocuments([store.toDocumentRecord(backendDoc('resume:1'))])
store.upsertDocuments([store.toDocumentRecord(backendDoc('resume:1', 'success_with_warnings'))])
assert(store.documents.length === 1, 'upsertDocuments should not create duplicate document rows')
assert(store.documents[0].parseStatus === 'success_with_warnings', 'upsertDocuments should replace existing rows')

store.listLoading = false
store.uploadingCount = 0
void store.uploadDocument('resume', new File(['hello'], 'resume.pdf'), 'task-1', () => undefined).catch(() => undefined)
assert(store.listLoading === false, 'uploadDocument must not control listLoading')

const starts: string[] = []
const closed: string[] = []
const refreshed: string[] = []
const uploaded: string[] = []
const progress: number[] = []
const queue = createDocumentUploadQueue({
  createTaskId: () => `task-${starts.length + 1}`,
  subscribe: (taskId, callbacks) => {
    starts.push(taskId)
    if (taskId === 'task-1') {
      callbacks.onMessage({
        taskId,
        stage: 'failed',
        status: 'failed',
        progress: 100,
        overallProgress: 100,
        message: 'first failed',
      } as SseProgressEvent)
    }
    return { close: () => closed.push(taskId) }
  },
  upload: async (_type, file, taskId, onUploadProgress) => {
    uploaded.push(`${taskId}:${file.name}`)
    onUploadProgress({ loaded: 25, total: 100 })
    progress.push(queue.tasks.get(taskId)?.uploadProgress || 0)
    if (file.name === 'bad.pdf') throw new Error('bad upload')
    return { documents: [backendDoc(`resume:${taskId}`)] }
  },
  refreshDocumentsSilently: async () => {
    refreshed.push('yes')
  },
})

await queue.enqueueFiles('resume', [new File(['bad'], 'bad.pdf'), new File(['good'], 'good.pdf')])

assert(starts.length === 2, 'each file should get its own SSE subscription')
assert(uploaded.length === 2, 'single file failure should not stop later uploads')
assert(queue.tasks.size === 2, 'each file should keep independent task state')
assert(queue.tasks.get('task-1')?.status === 'failed', 'first task should remain failed')
assert(queue.tasks.get('task-2')?.status === 'running' || queue.tasks.get('task-2')?.status === 'success', 'second task should have independent state')
assert(progress[0] === 25, 'upload progress should use loaded / total')

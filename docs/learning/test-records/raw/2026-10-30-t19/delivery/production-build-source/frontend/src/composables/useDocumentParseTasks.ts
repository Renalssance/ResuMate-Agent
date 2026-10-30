import type { AxiosProgressEvent } from 'axios'
import { activeTaskKey, readActiveTask, saveActiveTask } from '../services/activeTasks'
import { readAccessToken } from '../services/authToken'
import { reactive } from 'vue'
import { uploadDocumentsApi, type ParseDocumentsResponse } from '../api/documents'
import { subscribeTaskProgress, type TaskConnection } from '../services/sse'
import type { DocumentRecord, DocumentType } from '../types/document'
import { PARSE_STEPS, type AgentProgressEvent, type ProgressStep, type SseProgressEvent, type TaskStatus } from '../types/task'
import { createId } from '../utils/format'
import { useAgentStatus } from './useAgentStatus'

const globalAgentStatus = useAgentStatus()

export type ParseStage =
  | 'pending'
  | 'upload_client'
  | 'server_save'
  | 'extract'
  | 'llm_analyze'
  | 'embedding'
  | 'milvus_save'
  | 'chroma_save'
  | 'cancelled'
  | 'local_save'
  | 'completed'
  | 'failed'

export interface DocumentParseTask {
  taskId: string
  accepted?: boolean
  filename: string
  documentType: DocumentType
  status: TaskStatus
  stage: ParseStage
  uploadProgress: number
  stageProgress?: number
  overallProgress: number
  message: string
  errorReason: string
  agentEvents: AgentProgressEvent[]
  steps: ProgressStep[]
}

interface QueueItem {
  type: DocumentType
  file: File
  resolve: (succeeded: boolean) => void
}

interface UploadProgressLike {
  loaded: number
  total?: number
}

interface UploadQueueDeps {
  createTaskId?: () => string
  subscribe?: (taskId: string, callbacks: Parameters<typeof subscribeTaskProgress>[1]) => TaskConnection
  upload?: (
    type: DocumentType,
    file: File,
    taskId: string,
    onUploadProgress: (event: UploadProgressLike) => void,
    onAccepted?: (taskId: string) => void,
  ) => Promise<ParseDocumentsResponse>
  refreshDocumentsSilently?: () => Promise<void>
  reparse?: (documentId: string, taskId: string, onAccepted?: (taskId: string) => void) => Promise<unknown>
  concurrency?: number
}

export function useDocumentParseTasks(deps: UploadQueueDeps = {}) {
  return createDocumentUploadQueue(deps)
}

export function createDocumentUploadQueue(deps: UploadQueueDeps = {}) {
  const storageKey = activeTaskKey('document-tasks')
  const ownerToken = readAccessToken()
  type AcceptedDocumentTask = Pick<DocumentParseTask, 'taskId' | 'filename' | 'documentType'>
  const tasks = reactive(new Map<string, DocumentParseTask>())
  function remember(task: DocumentParseTask) {
    const saved = readActiveTask<AcceptedDocumentTask[]>(storageKey) || []
    saveActiveTask(storageKey, [...saved.filter(item => item.taskId !== task.taskId), { taskId: task.taskId, filename: task.filename, documentType: task.documentType }])
  }
  function forget(taskId: string) {
    const saved = (readActiveTask<AcceptedDocumentTask[]>(storageKey) || []).filter(item => item.taskId !== taskId)
    if (saved.length) saveActiveTask(storageKey, saved)
    else localStorage.removeItem(storageKey)
  }
  const queue: QueueItem[] = []
  const connections = new Map<string, TaskConnection>()
  let activeCount = 0
  let closed = false
  const concurrency = Math.min(Math.max(deps.concurrency || 1, 1), 2)
  const createTaskId = deps.createTaskId || (() => createId('task_parse'))
  const subscribe = deps.subscribe || subscribeTaskProgress
  const upload = deps.upload || defaultUpload
  const refreshDocumentsSilently = deps.refreshDocumentsSilently || (async () => undefined)
  const reparse = deps.reparse

  async function enqueueFiles(type: DocumentType, files: File[]) {
    return Promise.all(
      files.map(
        (file) =>
          new Promise<boolean>((resolve) => {
            queue.push({ type, file, resolve })
            drain()
          }),
      ),
    )
  }

  function drain() {
    if (closed || ownerToken !== readAccessToken()) { closeAll(); return }
    while (activeCount < concurrency && queue.length) {
      const item = queue.shift()
      if (!item) return
      activeCount += 1
      void runItem(item).then(item.resolve).finally(() => {
        activeCount -= 1
        drain()
      })
    }
  }

  async function runItem(item: QueueItem) {
    const taskId = createTaskId()
    const rawTask = createTask(taskId, item.file.name, item.type)
    tasks.set(taskId, rawTask)
    const task = tasks.get(taskId)!

    try {
      await upload(item.type, item.file, taskId, (event) => updateUploadProgress(task, event), (acceptedId) => acceptTask(task, acceptedId))
      return true
    } catch (err) {
      failTask(task, err instanceof Error ? err.message : String(err))
      return false
    }
  }

  function acceptTask(task: DocumentParseTask, acceptedId: string) {
    tasks.delete(task.taskId)
    task.taskId = acceptedId
    task.accepted = true
    remember(task)
    tasks.set(acceptedId, task)
    subscribeToTask(task)
  }

  function subscribeToTask(task: DocumentParseTask) {
    if (closed) return
    const taskId = task.taskId
    connections.set(
      taskId,
      subscribe(taskId, {
        onMessage: (event) => {
          updateFromSse(task, event)
          if (event.status === 'success' || event.status === 'failed') forget(task.taskId)
          if (event.stage === 'completed' && event.status === 'success') {
            void refreshDocumentsSilently()
          }
        },
        onReconnect: () => { task.message = '实时进度连接已中断，正在重新连接，任务会继续运行' },
        onError: error => { failTask(task, error.message); forget(task.taskId) },
      }),
    )
  }

  function closeTask(taskId: string) {
    connections.get(taskId)?.close()
    connections.delete(taskId)
  }

  function closeAll() {
    closed = true
    for (const taskId of connections.keys()) closeTask(taskId)
    for (const item of queue.splice(0)) item.resolve(false)
  }

  async function reparseDocument(document: DocumentRecord) {
    if (!reparse) return
    const taskId = createTaskId()
    const rawTask = createTask(taskId, document.filename, document.type)
    rawTask.message = 'Reparse submitted'
    tasks.set(taskId, rawTask)
    const task = tasks.get(taskId)!

    try {
      await reparse(document.id, taskId, (acceptedId) => acceptTask(task, acceptedId))
    } catch (err) {
      failTask(task, err instanceof Error ? err.message : String(err))
    }
  }

  for (const saved of readActiveTask<AcceptedDocumentTask[]>(storageKey) || []) {
    const task = createTask(saved.taskId, saved.filename, saved.documentType)
    task.accepted = true
    task.status = 'running'
    task.message = '正在恢复已受理任务的进度'
    tasks.set(task.taskId, task)
    subscribeToTask(tasks.get(task.taskId)!)
  }
  return { tasks, enqueueFiles, reparseDocument, closeTask, closeAll }
}

async function defaultUpload(
  type: DocumentType,
  file: File,
  taskId: string,
  onUploadProgress: (event: UploadProgressLike) => void,
  onAccepted?: (taskId: string) => void,
) {
  const formData = new FormData()
  formData.append('document_type', type)
  formData.append('task_id', taskId)
  formData.append('files', file)
  return uploadDocumentsApi(formData, (event: AxiosProgressEvent) => onUploadProgress(event), onAccepted)
}

function createTask(taskId: string, filename: string, documentType: DocumentType): DocumentParseTask {
  return {
    taskId,
    filename,
    documentType,
    status: 'pending',
    stage: 'pending',
    uploadProgress: 0,
    overallProgress: 0,
    message: '等待上传',
    errorReason: '',
    agentEvents: [],
    steps: PARSE_STEPS.map((step) => ({ ...step, status: 'pending', progress: 0 })),
  }
}

function updateUploadProgress(task: DocumentParseTask, event: UploadProgressLike) {
  task.stage = 'upload_client'
  task.status = 'running'
  task.message = event.total ? `Uploading ${Math.round((event.loaded * 100) / event.total)}%` : 'Uploading'
  if (event.total) {
    task.uploadProgress = Math.round((event.loaded * 100) / event.total)
    task.overallProgress = Math.max(task.overallProgress, Math.min(10, Math.round(task.uploadProgress / 10)))
    const stepStatus = task.uploadProgress >= 100 ? 'success' : 'running'
    updateStep(task, 'upload_client', stepStatus, task.uploadProgress, task.message)
  } else {
    updateStep(task, 'upload_client', 'running', 0, task.message)
  }
}

function updateFromSse(task: DocumentParseTask, event: SseProgressEvent) {
  task.status = event.status
  task.stage = (event.stage || 'pending') as ParseStage
  task.stageProgress = event.stageProgress
  task.overallProgress = Math.max(task.overallProgress, event.overallProgress ?? event.progress ?? 0)
  task.message = event.message
  if (event.status === 'failed') task.errorReason = event.message
  const agent = readAgentProgress(event)
  if (agent) {
    task.agentEvents = [agent, ...task.agentEvents].slice(0, 12)
    globalAgentStatus.record(agent, event.taskId)
  }
  if (event.stage === 'completed') {
    task.steps = task.steps.map((step) => ({ ...step, status: 'success', progress: 100 }))
    task.overallProgress = 100
    return
  }
  const status = event.status === 'success' ? 'success' : event.status === 'failed' ? 'failed' : 'running'
  updateStep(task, event.stage, status, event.stageProgress ?? event.progress, event.message)
}

function readAgentProgress(event: SseProgressEvent): AgentProgressEvent | null {
  const agent = event.data?.agent
  if (!agent || typeof agent !== 'object') return null
  return agent as AgentProgressEvent
}

function failTask(task: DocumentParseTask, reason: string) {
  if (task.status === 'success') return
  task.status = 'failed'
  task.stage = 'failed'
  task.errorReason = reason
  task.message = reason
  updateStep(task, task.steps.find((step) => step.status === 'running')?.key || 'upload_client', 'failed', 100, reason)
}

function updateStep(task: DocumentParseTask, key: string, status: TaskStatus, progress: number, message: string) {
  const activeIndex = task.steps.findIndex((step) => step.key === key)
  task.steps = task.steps.map((step, index) => {
    if (activeIndex >= 0 && index < activeIndex) return { ...step, status: 'success', progress: 100 }
    if (step.key !== key) return step
    return { ...step, status, progress: Math.max(step.progress, progress), message }
  })
}

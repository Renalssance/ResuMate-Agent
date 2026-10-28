import { request } from '../services/request'
import { waitForTaskResult, type AcceptedTask } from '../services/taskResult'
import type { DocumentType } from '../types/document'
import type { AxiosProgressEvent } from 'axios'

export interface UploadDocumentsResponse {
  documentIds: string[]
  taskId: string
}

export interface BackendDocumentParseResult {
  id: string
  type: DocumentType
  filename: string
  size: number
  raw_text: string
  parsed_content: Record<string, unknown>
  vectorized: boolean
  local_stored: boolean
  parse_status: string
  created_at: string
}

export interface ParseDocumentsResponse {
  documents: BackendDocumentParseResult[]
  taskId?: string
}

export interface JDUploadResponse {
  id: number
  title: string
  company: string
  message: string
}

export async function uploadDocumentsApi(formData: FormData, onUploadProgress?: (event: AxiosProgressEvent) => void) {
  const accepted = await request.post<AcceptedTask, AcceptedTask>('/documents', formData, {
    onUploadProgress,
    headers: { Prefer: 'respond-async' },
  })
  return waitForTaskResult<ParseDocumentsResponse>(accepted.taskId, (data) => ({
    documents: data.documents as BackendDocumentParseResult[],
    taskId: accepted.taskId,
  }))
}

export function fetchDocumentsApi() {
  return request.get<BackendDocumentParseResult[], BackendDocumentParseResult[]>('/documents')
}

export function fetchDocumentApi(documentId: string) {
  return request.get<BackendDocumentParseResult, BackendDocumentParseResult>(`/documents/${documentId}`)
}

export async function reparseDocumentApi(documentId: string, taskId = '') {
  const suffix = taskId ? `?task_id=${encodeURIComponent(taskId)}` : ''
  const accepted = await request.post<AcceptedTask, AcceptedTask>(`/documents/${documentId}/parse${suffix}`, undefined, {
    headers: { Prefer: 'respond-async' },
  })
  return waitForTaskResult(accepted.taskId, (data) => data.document as BackendDocumentParseResult)
}

export function deleteDocumentApi(documentId: string) {
  return request.delete<void, void>(`/documents/${documentId}`)
}

export function updateStructuredDataApi(documentId: string, structuredData: Record<string, unknown>) {
  return request.patch<BackendDocumentParseResult, BackendDocumentParseResult>(
    `/documents/${documentId}/structured-data`,
    { structuredData },
  )
}

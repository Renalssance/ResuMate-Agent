import { request } from '../services/request'
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

export function uploadDocumentsApi(formData: FormData, onUploadProgress?: (event: AxiosProgressEvent) => void) {
  return request.post<ParseDocumentsResponse, ParseDocumentsResponse>('/documents', formData, { onUploadProgress })
}

export function fetchDocumentsApi() {
  return request.get<BackendDocumentParseResult[], BackendDocumentParseResult[]>('/documents')
}

export function fetchDocumentApi(documentId: string) {
  return request.get<BackendDocumentParseResult, BackendDocumentParseResult>(`/documents/${documentId}`)
}

export function reparseDocumentApi(documentId: string, taskId = '') {
  const suffix = taskId ? `?task_id=${encodeURIComponent(taskId)}` : ''
  return request.post<BackendDocumentParseResult, BackendDocumentParseResult>(`/documents/${documentId}/parse${suffix}`)
}

export function deleteDocumentApi(documentId: string) {
  return request.delete<void, void>(`/documents/${documentId}`)
}

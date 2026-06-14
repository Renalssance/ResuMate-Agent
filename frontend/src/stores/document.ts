import type { AxiosProgressEvent } from 'axios'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  deleteDocumentApi,
  fetchDocumentsApi,
  reparseDocumentApi,
  uploadDocumentsApi,
  type BackendDocumentParseResult,
} from '../api/documents'

import {
  isDocumentParseSuccess,
  type DocumentRecord,
  type DocumentType,
} from '../types/document'

export const useDocumentStore = defineStore('document', () => {
  const documents = ref<DocumentRecord[]>([])
  const listLoading = ref(false)
  const uploadingCount = ref(0)
  const deletingIds = ref<Set<string>>(new Set())
  const reparsingIds = ref<Set<string>>(new Set())
  const error = ref('')
  const parsedJds = computed(() => documents.value.filter((doc) => doc.type === 'jd' && isDocumentParseSuccess(doc.parseStatus)))
  const parsedResumes = computed(() => documents.value.filter((doc) => doc.type === 'resume' && isDocumentParseSuccess(doc.parseStatus)))

  async function loadDocuments() {
    listLoading.value = true
    try {
      documents.value = (await fetchDocumentsApi()).map(toDocumentRecord)
      error.value = ''
    } finally {
      listLoading.value = false
    }
  }

  async function refreshDocumentsSilently() {
    try {
      upsertDocuments((await fetchDocumentsApi()).map(toDocumentRecord))
      error.value = ''
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    }
  }

  async function uploadDocument(
    type: DocumentType,
    file: File,
    taskId = '',
    onUploadProgress?: (event: AxiosProgressEvent) => void,
  ) {
    const formData = new FormData()
    formData.append('document_type', type)
    if (taskId) formData.append('task_id', taskId)
    formData.append('files', file)
    uploadingCount.value += 1
    try {
      const response = await uploadDocumentsApi(formData, onUploadProgress)
      const created = response.documents.map(toDocumentRecord)
      upsertDocuments(created)
      return response
    } finally {
      uploadingCount.value = Math.max(0, uploadingCount.value - 1)
    }
  }

  async function uploadDocuments(type: DocumentType, files: File[], taskId = '') {
    const documentIds: string[] = []
    for (const file of files) {
      const response = await uploadDocument(type, file, taskId)
      documentIds.push(...response.documents.map((doc) => doc.id))
    }
    return { documentIds }
  }

  async function reparseDocument(id: string, taskId = '') {
    reparsingIds.value = new Set(reparsingIds.value).add(id)
    try {
      const updated = toDocumentRecord(await reparseDocumentApi(id, taskId))
      upsertDocument(updated)
      return updated
    } finally {
      const next = new Set(reparsingIds.value)
      next.delete(id)
      reparsingIds.value = next
    }
  }

  async function deleteDocument(id: string) {
    deletingIds.value = new Set(deletingIds.value).add(id)
    try {
      await deleteDocumentApi(id)
      documents.value = documents.value.filter((doc) => doc.id !== id)
    } finally {
      const next = new Set(deletingIds.value)
      next.delete(id)
      deletingIds.value = next
    }
  }

  function upsertDocument(document: DocumentRecord) {
    upsertDocuments([document])
  }

  function upsertDocuments(nextDocuments: DocumentRecord[]) {
    const byId = new Map(documents.value.map((doc) => [doc.id, doc]))
    for (const doc of nextDocuments) byId.set(doc.id, doc)
    const incomingIds = new Set(nextDocuments.map((doc) => doc.id))
    documents.value = [
      ...nextDocuments,
      ...documents.value.filter((doc) => !incomingIds.has(doc.id)),
    ].map((doc) => byId.get(doc.id) || doc)
  }

  return {
    documents,
    listLoading,
    uploadingCount,
    deletingIds,
    reparsingIds,
    error,
    parsedJds,
    parsedResumes,
    loadDocuments,
    refreshDocumentsSilently,
    uploadDocument,
    uploadDocuments,
    reparseDocument,
    deleteDocument,
    upsertDocument,
    upsertDocuments,
    toDocumentRecord,
  }
})

export function toDocumentRecord(doc: BackendDocumentParseResult): DocumentRecord {
  return {
    id: doc.id,
    type: doc.type,
    filename: doc.filename,
    size: doc.size,
    createdAt: doc.created_at || new Date().toISOString(),
    parseStatus: (doc.parse_status || 'success') as DocumentRecord['parseStatus'],
    rawText: doc.raw_text,
    parsedContent: doc.parsed_content,
    vectorized: doc.vectorized,
    localStored: doc.local_stored,
  }
}

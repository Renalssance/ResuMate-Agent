import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  deleteDocumentApi,
  fetchDocumentsApi,
  reparseDocumentApi,
  uploadDocumentsApi,
  type BackendDocumentParseResult,
} from '../api/documents'
import type { DocumentRecord, DocumentType } from '../types/document'

export const useDocumentStore = defineStore('document', () => {
  const documents = ref<DocumentRecord[]>([])
  const loading = ref(false)
  const error = ref('')
  const parsedJds = computed(() => documents.value.filter((doc) => doc.type === 'jd' && doc.parseStatus === 'success'))
  const parsedResumes = computed(() => documents.value.filter((doc) => doc.type === 'resume' && doc.parseStatus === 'success'))

  async function loadDocuments() {
    loading.value = true
    try {
      documents.value = (await fetchDocumentsApi()).map(toDocumentRecord)
      error.value = ''
    } finally {
      loading.value = false
    }
  }

  async function uploadDocuments(type: DocumentType, files: File[], taskId = '') {
    const formData = new FormData()
    formData.append('document_type', type)
    if (taskId) formData.append('task_id', taskId)
    files.forEach((file) => formData.append('files', file))
    loading.value = true
    try {
      const response = await uploadDocumentsApi(formData)
      const created = response.documents.map(toDocumentRecord)
      documents.value = [...created, ...documents.value]
      return { documentIds: created.map((doc) => doc.id) }
    } finally {
      loading.value = false
    }
  }

  async function reparseDocument(id: string, taskId = '') {
    const updated = toDocumentRecord(await reparseDocumentApi(id, taskId))
    documents.value = documents.value.map((doc) => (doc.id === id ? updated : doc))
    return updated
  }

  async function deleteDocument(id: string) {
    await deleteDocumentApi(id)
    documents.value = documents.value.filter((doc) => doc.id !== id)
  }

  return { documents, loading, error, parsedJds, parsedResumes, loadDocuments, uploadDocuments, reparseDocument, deleteDocument }
})

function toDocumentRecord(doc: BackendDocumentParseResult): DocumentRecord {
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

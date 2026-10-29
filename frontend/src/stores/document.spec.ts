import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useDocumentStore } from './document'
import { saveAccessToken } from '../services/authToken'
const api = vi.hoisted(() => ({ fetchDocumentsApi: vi.fn() }))
vi.mock('../api/documents', () => ({ ...api, deleteDocumentApi: vi.fn(), reparseDocumentApi: vi.fn(), updateStructuredDataApi: vi.fn(), uploadDocumentsApi: vi.fn() }))
beforeEach(() => { setActivePinia(createPinia()); vi.resetAllMocks(); localStorage.clear() })
const doc = { id: 'resume:1', type: 'resume', filename: '账户A的简历', parse_status: 'success', parsed_content: {}, created_at: '2026-10-30T00:00:00Z' }
describe('document account context', () => {
 it('does not restore a previous account document response after logout', async () => {
  let resolve!: (value: unknown) => void; api.fetchDocumentsApi.mockImplementation(() => new Promise(r => { resolve = r })); saveAccessToken('a'); const store = useDocumentStore(); const pending = store.loadDocuments(); localStorage.clear(); store.clearDocuments(); resolve([doc]); await pending; expect(store.documents).toEqual([]); expect(store.listLoading).toBe(false)
 })
 it('does not display a previous account refresh error in the new account', async () => {
  let reject!: (value: unknown) => void; api.fetchDocumentsApi.mockImplementation(() => new Promise((_, r) => { reject = r })); saveAccessToken('a'); const store = useDocumentStore(); const pending = store.refreshDocumentsSilently(); saveAccessToken('b'); reject(new Error('账户A请求失败')); await pending; expect(store.error).toBe('')
 })
})

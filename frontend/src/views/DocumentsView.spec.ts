import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { expect, it, vi } from 'vitest'
import DocumentsView from './DocumentsView.vue'
import DocumentDetailDrawer from '../components/DocumentDetailDrawer.vue'

vi.mock('../api/documents', () => ({ fetchDocumentsApi: async () => [{
  id: 'resume:7', type: 'resume', filename: 'linked-resume.txt', size: 12, raw_text: 'content',
  parsed_content: {}, vectorized: false, local_stored: true, parse_status: 'success', created_at: '2026-10-31',
}] }))
it('opens the linked document after the library loads', async () => {
  HTMLDialogElement.prototype.showModal = function () { this.open = true }
  HTMLDialogElement.prototype.close = function () { this.open = false }
  setActivePinia(createPinia())
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/documents', component: DocumentsView }] })
  await router.push('/documents?document=resume%3A7'); await router.isReady()
  const wrapper = mount(DocumentsView, { global: { plugins: [router] } })
  await flushPromises()
  expect(wrapper.getComponent(DocumentDetailDrawer).props('document')?.filename).toBe('linked-resume.txt')
  expect(wrapper.get('dialog').attributes('open')).toBeDefined()
  wrapper.unmount()
})

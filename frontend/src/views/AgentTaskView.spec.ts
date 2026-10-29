import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import AgentTaskView from './AgentTaskView.vue'
const fixtures = vi.hoisted(() => ({ store: {} as Record<string, unknown> }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => ({ token: 'token', isAuthenticated: true }) }))
vi.mock('../stores/document', () => ({ useDocumentStore: () => ({ parsedJds: [], parsedResumes: [], listLoading: false, error: '', loadDocuments: vi.fn() }) }))
vi.mock('../stores/agentRun', () => ({ useAgentRunStore: () => fixtures.store }))
describe('task workspace actions', () => {
 it('does not offer a cancelled pending question as a live continue action', async () => {
  fixtures.store = reactive({ snapshot: { runId: 'r', status: 'cancelled', input: {}, cancelRequested: true, actions: [{ actionId: 'a', kind: 'input', revision: 1, payload: { question: '你负责什么工作？' } }] }, runs: [], drafts: {}, actionErrors: {}, conflictedActions: [], events: [], artifacts: [], busy: false, openRun: vi.fn(), loadRuns: vi.fn(), disconnect: vi.fn() })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/documents', component: { template: '<p>文档</p>' } }, { path: '/agent/tasks/:runId', component: AgentTaskView }] }); await router.push('/agent/tasks/r'); await router.isReady()
  const wrapper = mount(AgentTaskView, { global: { plugins: [router] } })
  expect(wrapper.text()).toContain('任务已取消'); expect(wrapper.find('textarea').exists()).toBe(false); expect(wrapper.text()).not.toContain('继续任务'); wrapper.unmount()
 })
})

it('downloads a completed PDF with Bearer authentication and offers its confirmed source version', async () => {
 localStorage.setItem('accessToken', 'download-token')
 const blob = new Blob(['%PDF-1.7 test'], { type: 'application/pdf' })
 vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(blob)))
 vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn().mockReturnValue('blob:pdf-file'), revokeObjectURL: vi.fn() }))
 const clicked: { href?: string; download?: string } = {}
 const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function(this: HTMLAnchorElement) { clicked.href = this.href; clicked.download = this.download })
 fixtures.store = reactive({ snapshot: { runId: 'pdf-run', kind: 'resume_export', status: 'succeeded', input: { resumeVersionId: 'v1' }, cancelRequested: false, actions: [] }, runs: [], drafts: {}, actionErrors: {}, conflictedActions: [], events: [], artifacts: [{ kind: 'resume_pdf', id: 'pdf-run', runId: 'pdf-run', resumeVersionId: 'v1', revision: 3, filename: '投递简历.pdf', downloadUrl: '/api/agent/runs/pdf-run/download', createdAt: '' }], busy: false, openRun: vi.fn(), loadRuns: vi.fn(), disconnect: vi.fn() })
 const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/documents', component: { template: '<p>文档</p>' } }, { path: '/agent/tasks/:runId', component: AgentTaskView }, { path: '/resume-versions/:versionId', component: { template: '<p>版本</p>' } }] }); await router.push('/agent/tasks/pdf-run'); await router.isReady()
 const wrapper = mount(AgentTaskView, { global: { plugins: [router] } })
 expect(wrapper.text()).toContain('PDF 已导出')
 expect(wrapper.findAll('a').some(link => link.attributes('href') === '/resume-versions/v1')).toBe(true)
 await wrapper.findAll('button').find(button => button.text() === '下载 PDF')!.trigger('click'); await flushPromises()
 expect(fetch).toHaveBeenCalledWith('/api/agent/runs/pdf-run/download', expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer download-token' }) }))
 expect(clicked).toEqual({ href: 'blob:pdf-file', download: '投递简历.pdf' })
 wrapper.unmount(); click.mockRestore(); localStorage.clear(); vi.unstubAllGlobals()
})

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

async function openFailure(errorCode: string, status = 'failed', kind = 'tailoring', sessionInvalidated = false) {
 fixtures.store = reactive({ snapshot: { runId: 'r', kind, status, errorCode, sessionInvalidated, input: { jdId: 1, resumeId: 2 }, cancelRequested: status === 'cancelled', actions: [] }, runs: [], drafts: {}, actionErrors: {}, conflictedActions: [], events: [], artifacts: [], busy: false, openRun: vi.fn(), loadRuns: vi.fn(), disconnect: vi.fn(), createRun: vi.fn().mockResolvedValue('fresh-run') })
 const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/documents', component: { template: '<p>文档</p>' } }, { path: '/settings', component: { template: '<p>设置</p>' } }, { path: '/resume-versions/:versionId', component: { template: '<p>版本</p>' } }, { path: '/agent/tasks/:runId', component: AgentTaskView }] }); await router.push('/agent/tasks/r'); await router.isReady()
 const wrapper = mount(AgentTaskView, { global: { plugins: [router] } }); return { wrapper, router }
}
it('links unconfigured capacity failures to model settings', async () => {
 const { wrapper } = await openFailure('model_context_not_configured'); expect(wrapper.text()).toContain('尚未配置模型的上下文容量'); expect(wrapper.findAll('a').some(link => link.attributes('href') === '/settings')).toBe(true); wrapper.unmount()
})
it('explains an exceeded context budget without silently losing materials', async () => {
 const { wrapper } = await openFailure('context_budget_exceeded'); expect(wrapper.text()).toContain('减少本次资料'); expect(wrapper.text()).toContain('厂商'); wrapper.unmount()
})
it.each(['failed', 'cancelled'])('offers a clean new task instead of retrying an invalidated %s session', async (status) => {
 const { wrapper, router } = await openFailure('session_context_invalidated', status)
 expect(wrapper.text()).toContain('旧会话不能恢复'); expect(wrapper.text()).not.toContain('重试任务'); expect(wrapper.find('.task-settings-link').exists()).toBe(false)
 await wrapper.findAll('button').find(button => button.text() === '重新准备材料')!.trigger('click'); await flushPromises()
 expect(fixtures.store.createRun).toHaveBeenCalledWith('jd:1', 'resume:2'); expect(router.currentRoute.value.path).toBe('/agent/tasks/fresh-run'); wrapper.unmount()
})
it('preserves the existing PDF failure guidance', async () => {
 const { wrapper } = await openFailure('renderer_failed', 'failed', 'resume_export'); expect(wrapper.text()).toContain('PDF 导出未完成'); expect(wrapper.text()).toContain('重试任务'); expect(wrapper.text()).not.toContain('上下文容量'); wrapper.unmount()
})

it.each(['failed', 'cancelled'])('uses the session invalidation flag while preserving the original %s error', async (status) => {
 const { wrapper, router } = await openFailure('context_budget_exceeded', status, 'tailoring', true)
 expect(wrapper.text()).toContain('旧会话不能恢复'); expect(wrapper.text()).not.toContain('重试任务'); expect(wrapper.find('.task-settings-link').exists()).toBe(false)
 await wrapper.findAll('button').find(button => button.text() === '重新准备材料')!.trigger('click'); await flushPromises()
 expect(fixtures.store.createRun).toHaveBeenCalledWith('jd:1', 'resume:2'); expect(router.currentRoute.value.path).toBe('/agent/tasks/fresh-run'); wrapper.unmount()
})
it('keeps a completed historical artifact visible after its session is invalidated', async () => {
 const { wrapper } = await openFailure('', 'succeeded', 'tailoring', true)
 fixtures.store.artifacts = [{ id: 'version-1', runId: 'r', resumeId: 2, jdId: 1, revision: 1, status: 'confirmed', structuredContent: { summary: '已生成的历史简历内容' }, factRefs: [], createdAt: '' }]
 await flushPromises()
 expect(wrapper.text()).toContain('材料已生成'); expect(wrapper.text()).toContain('已生成的历史简历内容'); expect(wrapper.get('[data-review-link]').attributes('href')).toBe('/resume-versions/version-1'); expect(wrapper.find('.task-failure').exists()).toBe(false); wrapper.unmount()
})

it.each([
 ['document_parse', { documentId: 'resume:7', parseMode: 'upload' }, { documents: [{ id: 'resume:7', filename: '恢复后的简历.txt', parse_status: 'success' }] }, '恢复后的简历.txt'],
 ['document_import', { filename: '导入材料.txt' }, { documents: [{ id: 'jd:9', filename: '导入材料.txt', parse_status: 'success' }] }, '导入材料.txt'],
 ['match_analysis', { jdId: 1, resumeIds: [7] }, { run_id: 8, job_title: 'API工程师', candidates: [{ candidate_id: 2, candidate_name: '示例求职者', total_score: 76 }] }, '示例求职者'],
 ['question_generation', { analysisJobId: 8, candidateId: 2 }, { candidate_name: '示例求职者', formal_questions: [{ question_id: 'q1', question: '请说明一次接口故障的定位过程', assessment_points: ['定位'], scoring_rubric: ['真实证据'], reference_answer_direction: '解释观察和判断', suggested_followups: [] }], ambiguity_followups: [] }, '请说明一次接口故障的定位过程'],
 ['answer_followup', {}, { follow_up: '当时如何确认恢复？', reason: '核对观察依据', evidence: ['服务日志'], risks: ['尚无测量记录'], current_ability: '能解释处理步骤', next_suggestion: '补充验证依据' }, '当时如何确认恢复？'],
])('shows saved %s output without waiting for a nonexistent resume draft', async (kind, input, result, visible) => {
 fixtures.store = reactive({ snapshot: { runId: 'long-run', kind, status: 'succeeded', input, result, actions: [] }, runs: [], drafts: {}, actionErrors: {}, conflictedActions: [], events: [], artifacts: [], busy: false, openRun: vi.fn(), loadRuns: vi.fn(), disconnect: vi.fn() })
 const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/agent/tasks/:runId', component: AgentTaskView }, ...['/documents', '/matching', '/questions'].map(path => ({ path, component: { template: '<p>结果</p>' } }))] })
 await router.push('/agent/tasks/long-run'); await router.isReady()
 const wrapper = mount(AgentTaskView, { global: { plugins: [router] } })
 expect(wrapper.text()).toContain(visible)
 expect(wrapper.text()).not.toContain('正在读取草稿')
 expect(wrapper.text()).not.toContain('材料已生成')
 wrapper.unmount()
})

it('offers resume and job choices for a document import in the existing task workspace', async () => {
 const action = { actionId: 'type-1', kind: 'input', revision: 1, payload: { filename: '待确认.txt', question: '这份文件属于哪一类？', choices: [{ value: 'resume', label: '简历' }, { value: 'jd', label: '岗位' }] } }
 fixtures.store = reactive({ snapshot: { runId: 'import-1', kind: 'document_import', status: 'waiting_input', input: {}, actions: [action] }, runs: [], drafts: {}, actionErrors: {}, conflictedActions: [], events: [], artifacts: [], busy: false, openRun: vi.fn(), loadRuns: vi.fn(), disconnect: vi.fn(), submitAction: vi.fn() })
 const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/agent/tasks/:runId', component: AgentTaskView }, { path: '/documents', component: { template: '<p>文档</p>' } }] })
 await router.push('/agent/tasks/import-1'); await router.isReady()
 const wrapper = mount(AgentTaskView, { global: { plugins: [router] } })
 expect(wrapper.find('textarea').exists()).toBe(false)
 expect(wrapper.text()).toContain('待确认.txt')
 await wrapper.get('input[value="resume"]').setValue()
 expect(fixtures.store.drafts).toEqual({ 'type-1': 'resume' })
 await wrapper.get('input[value="jd"]').setValue()
 await wrapper.get('form.action-form').trigger('submit')
 expect(fixtures.store.drafts).toEqual({ 'type-1': 'jd' })
 expect(fixtures.store.submitAction).toHaveBeenCalledWith(action, 'submit')
 wrapper.unmount()
})

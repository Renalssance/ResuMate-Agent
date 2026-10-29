import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AgentTaskView from './AgentTaskView.vue'
import MatchingView from './MatchingView.vue'
const fixtures = vi.hoisted(() => ({ docs: {} as any, auth: {} as any, match: {} as any, run: {} as any }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => fixtures.auth }))
vi.mock('../stores/document', () => ({ useDocumentStore: () => fixtures.docs }))
vi.mock('../stores/match', () => ({ useMatchStore: () => fixtures.match }))
vi.mock('../stores/agentRun', () => ({ useAgentRunStore: () => fixtures.run }))
vi.mock('../composables/useTaskSse', async () => { const { ref } = await import('vue'); return { useTaskSse: () => ({ taskId: { value: '' }, progress: { value: 0 }, currentStep: { value: '' }, completedSteps: { value: [] }, steps: { value: [] }, message: { value: '' }, errorReason: { value: '' }, status: ref('pending') }) } })
beforeEach(() => { fixtures.auth = reactive({ token: 'a', isAuthenticated: true }); fixtures.docs = reactive({ parsedJds: [], parsedResumes: [], listLoading: false, error: '', loadDocuments: vi.fn() }); fixtures.match = reactive({ results: [], loadMatches: vi.fn() }); fixtures.run = reactive({ runs: [], snapshot: null, conflictedActions: [], loadRuns: vi.fn(), openRun: vi.fn(), disconnect: vi.fn() }) })
async function render(view: any, url: string) { const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/documents', component: { template: '<div />' } }, { path: '/matching', component: MatchingView }, { path: '/agent/tasks', component: AgentTaskView }] }); await router.push(url); await router.isReady(); return mount(view, { global: { plugins: [router], stubs: { TaskProgress: true } } }) }
describe.each([[MatchingView, '/matching'], [AgentTaskView, '/agent/tasks']])('saved job workflow selection %s', (view, path) => {
 it('preselects only owned parsed documents after the document list arrives', async () => {
  const w = await render(view, `${path}?jdId=3&resumeId=4`); await flushPromises(); fixtures.docs.parsedJds = [{ id: 'jd:3', filename: '岗位', parsedContent: {} }]; fixtures.docs.parsedResumes = [{ id: 'resume:4', filename: '简历', parsedContent: {} }]; await flushPromises()
  const selects = w.findAll('select'); expect((selects[0]!.element as HTMLSelectElement).value).toBe('jd:3'); expect((selects[1]!.element as HTMLSelectElement).value).toBe('resume:4'); w.unmount()
 })
 it('clears selections when account changes and rejects unrelated document queries', async () => {
  fixtures.docs.parsedJds = [{ id: 'jd:8', filename: '另一个岗位', parsedContent: {} }]; fixtures.docs.parsedResumes = [{ id: 'resume:9', filename: '另一份简历', parsedContent: {} }]; const w = await render(view, `${path}?jdId=3&resumeId=4`); await flushPromises(); expect((w.findAll('select')[0]!.element as HTMLSelectElement).value).toBe(''); w.unmount()
 })
})

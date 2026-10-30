import { mount, flushPromises } from '@vue/test-utils'
import { reactive, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AgentTaskView from './AgentTaskView.vue'
import MatchingView from './MatchingView.vue'
import QuestionsView from './QuestionsView.vue'
const fixtures = vi.hoisted(() => ({ docs: {} as any, auth: {} as any, match: {} as any, run: {} as any, task: {} as any, question: {} as any }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => fixtures.auth }))
vi.mock('../stores/document', () => ({ useDocumentStore: () => fixtures.docs }))
vi.mock('../stores/question', () => ({ useQuestionStore: () => fixtures.question }))
vi.mock('../stores/match', () => ({ useMatchStore: () => fixtures.match }))
vi.mock('../stores/agentRun', () => ({ useAgentRunStore: () => fixtures.run }))
vi.mock('../composables/useTaskSse', () => ({ useTaskSse: () => fixtures.task }))
beforeEach(() => { localStorage.clear(); fixtures.question = reactive({ questionSets: [], loading: false, error: '', loadQuestionSets: vi.fn(), createQuestionSet: vi.fn(), restoreQuestionSet: vi.fn() }); fixtures.task = { taskId: ref(''), progress: ref(0), currentStep: ref(''), completedSteps: ref([]), steps: ref([]), message: ref(''), errorReason: ref(''), status: ref('pending'), start: vi.fn(), startManual: vi.fn(), failManual: vi.fn(), reset: vi.fn() }; fixtures.auth = reactive({ token: 'a', isAuthenticated: true }); fixtures.docs = reactive({ parsedJds: [], parsedResumes: [], listLoading: false, error: '', loadDocuments: vi.fn() }); fixtures.match = reactive({ results: [], loadMatches: vi.fn(), createMatch: vi.fn() }); fixtures.run = reactive({ runs: [], snapshot: null, conflictedActions: [], loadRuns: vi.fn(), openRun: vi.fn(), disconnect: vi.fn() }) })
async function render(view: any, url: string) { const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/documents', component: { template: '<div />' } }, { path: '/matching', component: MatchingView }, { path: '/questions', component: QuestionsView }, { path: '/agent/tasks', component: AgentTaskView }] }); await router.push(url); await router.isReady(); return mount(view, { global: { plugins: [router], stubs: { TaskProgress: true } } }) }
describe.each([[MatchingView, '/matching'], [AgentTaskView, '/agent/tasks']])('saved job workflow selection %s', (view, path) => {
 it('preselects only owned parsed documents after the document list arrives', async () => {
  const w = await render(view, `${path}?jdId=3&resumeId=4`); await flushPromises(); fixtures.docs.parsedJds = [{ id: 'jd:3', filename: '岗位', parsedContent: {} }]; fixtures.docs.parsedResumes = [{ id: 'resume:4', filename: '简历', parsedContent: {} }]; await flushPromises()
  const selects = w.findAll('select'); expect((selects[0]!.element as HTMLSelectElement).value).toBe('jd:3'); expect((selects[1]!.element as HTMLSelectElement).value).toBe('resume:4'); w.unmount()
 })
 it('clears selections when account changes and rejects unrelated document queries', async () => {
  fixtures.docs.parsedJds = [{ id: 'jd:8', filename: '另一个岗位', parsedContent: {} }]; fixtures.docs.parsedResumes = [{ id: 'resume:9', filename: '另一份简历', parsedContent: {} }]; const w = await render(view, `${path}?jdId=3&resumeId=4`); await flushPromises(); expect((w.findAll('select')[0]!.element as HTMLSelectElement).value).toBe(''); w.unmount()
 })
})


it('restores an accepted matching task after returning to the page', async () => {
 localStorage.setItem('username', 'owner')
 localStorage.setItem('resumate:active-match-task:owner', JSON.stringify({ taskId: 'saved-match', jdId: 'jd:3', resumeIds: ['resume:4'] }))
 const w = await render(MatchingView, '/matching'); await flushPromises()
 expect(fixtures.task.start).toHaveBeenCalledWith('saved-match')
 expect(fixtures.match.createMatch).not.toHaveBeenCalled()
 w.unmount()
})

it('persists the server matching task ID only after acceptance', async () => {
 localStorage.setItem('username', 'owner')
 fixtures.docs.parsedJds = [{ id: 'jd:3', filename: '岗位' }]
 fixtures.docs.parsedResumes = [{ id: 'resume:4', filename: '简历' }]
 let accept!: (id: string) => void
 fixtures.match.createMatch.mockImplementation((_jd: any, _resumes: any, _key: string, callback: any) => { accept = callback; return new Promise(() => {}) })
 const w = await render(MatchingView, '/matching?jdId=3&resumeId=4'); await flushPromises()
 await w.findAll('button').find(b => b.text() === '开始匹配')!.trigger('click'); await flushPromises()
 expect(localStorage.getItem('resumate:active-match-task:owner')).toBeNull()
 accept('accepted-match')
 expect(JSON.parse(localStorage.getItem('resumate:active-match-task:owner')!).taskId).toBe('accepted-match')
 expect(fixtures.task.start).toHaveBeenCalledWith('accepted-match')
 w.unmount()
})


it('restores the question form context and uses the accepted task when its result arrives', async () => {
 localStorage.setItem('username', 'owner')
 const active = { taskId: 'saved-question', jdId: 'jd:3', resumeId: 'resume:4', matchId: '5:6', questionCount: 3 }
 localStorage.setItem('resumate:active-question-task:owner', JSON.stringify(active))
 fixtures.docs.parsedJds = [{ id: 'jd:3', filename: '岗位' }]
 fixtures.docs.parsedResumes = [{ id: 'resume:4', filename: '简历' }]
 fixtures.match.results = [{ id: '5:6', candidateName: '示例', score: 60 }]
 fixtures.task.start.mockImplementation((id: string) => { fixtures.task.taskId.value = id; fixtures.task.status.value = 'running' })
 const w = await render(QuestionsView, '/questions'); await flushPromises()
 expect(w.findAll('select').map(s => (s.element as HTMLSelectElement).value)).toEqual(['jd:3', 'resume:4', '5:6'])
 expect((w.get('input[type="number"]').element as HTMLInputElement).value).toBe('3')
 expect(fixtures.task.start).toHaveBeenCalledWith('saved-question')
 expect(fixtures.question.createQuestionSet).not.toHaveBeenCalled()
 fixtures.task.status.value = 'success'; await flushPromises()
 expect(fixtures.question.restoreQuestionSet).toHaveBeenCalledWith(fixtures.docs.parsedJds[0], fixtures.docs.parsedResumes[0], 3, fixtures.match.results[0], 'saved-question')
 expect(localStorage.getItem('resumate:active-question-task:owner')).toBeNull()
 w.unmount()
})

it('refreshes question history from the newly loaded candidate reports', async () => {
 const w = await render(QuestionsView, '/questions'); await flushPromises()
 const next = [{ id: '5:6' }]
 fixtures.match.loadMatches.mockImplementation(async () => { fixtures.match.results = next })
 await w.findAll('button').find(b => b.text() === '刷新')!.trigger('click'); await flushPromises()
 expect(fixtures.question.loadQuestionSets).toHaveBeenLastCalledWith(next)
 w.unmount()
})

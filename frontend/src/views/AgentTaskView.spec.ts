import { mount } from '@vue/test-utils'
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
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/agent/tasks/:runId', component: AgentTaskView }] }); await router.push('/agent/tasks/r'); await router.isReady()
  const wrapper = mount(AgentTaskView, { global: { plugins: [router] } })
  expect(wrapper.text()).toContain('任务已取消'); expect(wrapper.find('textarea').exists()).toBe(false); expect(wrapper.text()).not.toContain('继续任务'); wrapper.unmount()
 })
})

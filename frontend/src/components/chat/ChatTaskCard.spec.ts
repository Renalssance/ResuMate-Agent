import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import ChatTaskCard from './ChatTaskCard.vue'
import type { RunSnapshot, RunSubscriptionOptions } from '../../services/agentStream'
const streams = vi.hoisted(() => [] as RunSubscriptionOptions[])
vi.mock('../../services/agentStream', () => ({ subscribeRun: (options: RunSubscriptionOptions) => { streams.push(options); return { close: vi.fn(), done: new Promise(() => {}) } } }))
afterEach(() => { streams.length = 0; vi.unstubAllGlobals() })
describe('chat task card', () => {
  it('keeps queued tasks pending and only offers analysis when real results arrive', async () => {
    let value = { runId: 'task-1', sessionId: 's', sessionInvalidated: false, kind: 'match_analysis', status: 'queued', input: { jdId: 3, resumeIds: [4], analysisJobId: 5 }, inputVersions: {}, attempt: 1, lastSeq: 0, errorCode: null, cancelRequested: false, outputRefs: [], result: null, actions: [] } as RunSnapshot
    vi.stubGlobal('fetch', vi.fn(async () => Response.json(value)))
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
    const wrapper = mount(ChatTaskCard, { props: { reference: 'run:task-1' }, global: { plugins: [router] } }); await flushPromises()
    streams[0]!.onSnapshot!(value); await flushPromises()
    expect(wrapper.text()).toContain('等待匹配')
    expect(wrapper.find('.execution-spinner').exists()).toBe(true)
    expect(wrapper.find('[data-continue]').exists()).toBe(false)
    expect(wrapper.get('.task-actions a').attributes('href')).toBe('/matching?taskId=task-1&jdId=3&resumeId=4&analysisJobId=5')
    expect(wrapper.get('.task-actions a').text()).toContain('匹配进度')
    value = { ...value, status: 'succeeded', lastSeq: 5, result: { run_id: 2, job_title: '产品经理', candidates: [{ candidate_id: 3, candidate_name: '小林', total_score: 86 }] } }
    streams[0]!.onEvent({ runId: 'task-1', seq: 5, type: 'run.status', createdAt: '', payload: { status: 'succeeded' } }); await flushPromises()
    expect(wrapper.text()).toContain('86 分')
    expect(wrapper.find('.execution-spinner').exists()).toBe(false)
    expect(wrapper.get('a[href="/matching?matchId=2:3"]').text()).toContain('匹配报告')
    await wrapper.get('[data-continue]').trigger('click')
    expect(wrapper.emitted('continue')?.[0]?.[0]).toContain('task-1')
    wrapper.unmount()
  })
  it('shows a completed interview question and links to that interview', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
    const wrapper = mount(ChatTaskCard, { props: { reference: 'run:interview-task' }, global: { plugins: [router] } })
    streams[0]!.onSnapshot!({ runId: 'interview-task', status: 'succeeded', kind: 'interview_generation', lastSeq: 3, input: { interviewId: 'interview-7' }, result: { question: { text: '请介绍一次你解决复杂问题的经历。' }, feedback: { summary: '回答很有条理。' } } } as unknown as RunSnapshot)
    await flushPromises()
    expect(wrapper.text()).toContain('请介绍一次你解决复杂问题的经历。')
    expect(wrapper.text()).toContain('回答很有条理。')
    expect(wrapper.get('a[href="/interviews/interview-7"]').text()).toContain('模拟面试')
    wrapper.unmount()
  })
  it('routes a waiting task to the existing review and input workflow', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
    const wrapper = mount(ChatTaskCard, { props: { reference: 'run:task-2' }, global: { plugins: [router] } })
    streams[0]!.onSnapshot!({ runId: 'task-2', status: 'waiting_input', kind: 'tailoring', lastSeq: 2 } as RunSnapshot)
    await flushPromises()
    expect(wrapper.text()).toContain('等待你补充信息')
    expect(wrapper.find('.execution-spinner').exists()).toBe(false)
    expect(wrapper.get('a[href="/agent/tasks/task-2"]').text()).toContain('补充信息')
    wrapper.unmount()
  })
})

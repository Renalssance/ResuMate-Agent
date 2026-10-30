import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { reactive } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import InterviewView from './InterviewView.vue'
import { AgentRunError } from '../api/agentRuns'
import { fetchInterview, sendInterviewCommand, confirmInterviewMemory } from '../api/interviews'
const auth = vi.hoisted(() => ({ value: null as null | { token: string; isAuthenticated: boolean } }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => auth.value }))
vi.mock('../api/interviews', () => ({ fetchInterview: vi.fn(), sendInterviewCommand: vi.fn(), confirmInterviewMemory: vi.fn() }))
const question = { id: 1, turnIndex: 1, question: '如何保证重复请求只保存一次？', questionContext: { mode: 'opening', refs: [{ kind: 'job', quote: '可靠的业务流程', jdId: 2 }] }, answer: null, feedback: null }
const initial = () => ({ interviewId: 'interview-1', userId: 1, applicationId: 10, status: 'active', currentTurn: 1, lastSeq: 1, sessionInvalidated: false, sourceSnapshot: { applicationId: 10, resumeVersionId: 'v1', revision: 3, submittedAt: '2026-10-29T04:00:00Z', structuredContent: {}, factRefs: [], job: { jdId: 2, title: '后端开发', company: '示例公司', rawText: '可靠的业务流程', capturedAt: '2026-10-30T04:00:00Z', structuredData: {} } }, turns: [structuredClone(question)], generation: { runId: 'run-1', status: 'succeeded', errorCode: null, cancelRequested: false } })
async function setup() {
 const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/interviews/:id', component: InterviewView }, { path: '/applications', component: { template: '<p>投递记录</p>' } }] })
 await router.push('/interviews/interview-1'); await router.isReady()
 const wrapper = mount(InterviewView, { global: { plugins: [createPinia(), router] } }); await flushPromises()
 return { wrapper, router }
}
const button = (wrapper: Awaited<ReturnType<typeof setup>>['wrapper'], label: string) => wrapper.findAll('button').find(item => item.text() === label)!
beforeEach(() => {
 vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }); sessionStorage.clear()
 auth.value = reactive({ token: 'first-user-token', isAuthenticated: true })
 vi.mocked(fetchInterview).mockResolvedValue(initial() as never)
 vi.mocked(sendInterviewCommand).mockResolvedValue({ interviewId: 'interview-1', clientMessageId: 'ack', status: 'accepted', resultRef: 'run-2', acceptedSeq: 2 })
})
afterEach(() => { vi.clearAllMocks(); vi.useRealTimers() })
it('replays the exact pending command after a lost ack even when the draft is edited', async () => {
 const { wrapper } = await setup()
 vi.mocked(sendInterviewCommand).mockRejectedValueOnce(new Error('连接中断'))
 await wrapper.get('textarea').setValue('用事务和唯一键去重')
 await wrapper.get('form').trigger('submit'); await flushPromises()
 const first = vi.mocked(sendInterviewCommand).mock.calls[0]![1]
 expect(first).toMatchObject({ type: 'answer.submit', expectedTurn: 1, payload: { text: '用事务和唯一键去重' } })
 await wrapper.get('textarea').setValue('之后编辑的草稿')
 await button(wrapper, '重新发送原回答').trigger('click'); await flushPromises()
 expect(vi.mocked(sendInterviewCommand).mock.calls[1]![1]).toEqual(first)
 wrapper.unmount()
})
it('restores a frozen pending command after remount and does not create an answer on refresh', async () => {
 let view = await setup()
 vi.mocked(sendInterviewCommand).mockRejectedValueOnce(new Error('响应丢失'))
 await view.wrapper.get('textarea').setValue('刷新后仍保留')
 await view.wrapper.get('form').trigger('submit'); await flushPromises()
 const first = vi.mocked(sendInterviewCommand).mock.calls[0]![1]
 view.wrapper.unmount(); view = await setup()
 expect(sendInterviewCommand).toHaveBeenCalledTimes(1)
 expect(view.wrapper.text()).toContain('重新发送原回答')
 await button(view.wrapper, '重新发送原回答').trigger('click'); await flushPromises()
 expect(vi.mocked(sendInterviewCommand).mock.calls[1]![1]).toEqual(first)
 view.wrapper.unmount()
})
it('clears drafts and ignores old account responses when the account changes', async () => {
 const { wrapper } = await setup()
 await wrapper.get('textarea').setValue('旧账号的回答')
 let resolve!: (value: never) => void
 vi.mocked(fetchInterview).mockImplementationOnce(() => new Promise(done => { resolve = done }))
 await button(wrapper, '刷新进度').trigger('click'); await flushPromises()
 vi.mocked(fetchInterview).mockRejectedValueOnce(new Error('面试会话不存在'))
 auth.value!.token = 'second-user-token'; await flushPromises()
 resolve({ ...initial(), turns: [{ ...question, question: '不能串到新账号的题目' }] } as never); await flushPromises()
 expect(wrapper.text()).not.toContain('不能串到新账号的题目')
 expect(wrapper.text()).not.toContain('旧账号的回答')
 expect(Object.keys(sessionStorage).filter(key => key.startsWith('resumate:interview:'))).toEqual([])
 wrapper.unmount()
})
it('uses server generation state for stopping and only permits retry after a terminal result', async () => {
 vi.mocked(fetchInterview).mockResolvedValue({ ...initial(), generation: { runId: 'run-2', status: 'running', cancelRequested: true, errorCode: null } } as never)
 const { wrapper } = await setup()
 expect(wrapper.text()).toContain('正在停止')
 expect(button(wrapper, '重试生成')).toBeUndefined()
 vi.mocked(fetchInterview).mockResolvedValue({ ...initial(), generation: { runId: 'run-2', status: 'cancelled', cancelRequested: true, errorCode: null } } as never)
 await button(wrapper, '刷新进度').trigger('click'); await flushPromises()
 await button(wrapper, '重试生成').trigger('click'); await flushPromises()
 expect(sendInterviewCommand).toHaveBeenLastCalledWith('interview-1', expect.objectContaining({ type: 'generation.retry', expectedTurn: 1, payload: { runId: 'run-2' } }))
 wrapper.unmount()
})
it('shows the exact feedback memory before an explicit confirmation and never treats it as a resume fact', async () => {
 const feedback = { summary: '思路清楚', strengths: [{ text: '说明事务', refs: [] }], improvements: [], practiceFocus: '下次补充并发下唯一键冲突的处理。' }
 vi.mocked(fetchInterview).mockResolvedValue({ ...initial(), turns: [{ ...question, answer: '单事务', feedback }], status: 'finished' } as never)
 vi.mocked(confirmInterviewMemory).mockResolvedValue({ id: 'memory-1' } as never)
 const { wrapper } = await setup()
 expect(confirmInterviewMemory).not.toHaveBeenCalled()
 await button(wrapper, '保存练习要点').trigger('click'); await flushPromises()
 expect(wrapper.get('[aria-label="确认练习记忆"]').text()).toContain(feedback.practiceFocus)
 expect(confirmInterviewMemory).not.toHaveBeenCalled()
 await button(wrapper, '确认保存记忆').trigger('click'); await flushPromises()
 expect(confirmInterviewMemory).toHaveBeenCalledWith('interview-1', 1)
 expect(wrapper.text()).toContain('练习反馈')
 wrapper.unmount()
})

it('keeps a concrete rejection visible and leaves the draft editable without a pending replay', async () => {
 const { wrapper } = await setup()
 vi.mocked(sendInterviewCommand).mockRejectedValueOnce(new AgentRunError(409, 'turn_conflict', '当前轮已变化，请检查回答'))
 await wrapper.get('textarea').setValue('待检查的草稿')
 await wrapper.get('form').trigger('submit'); await flushPromises()
 expect(wrapper.text()).toContain('当前轮已变化，请检查回答')
 expect(wrapper.get<HTMLTextAreaElement>('textarea').element.value).toBe('待检查的草稿')
 expect(wrapper.text()).not.toContain('重新发送原回答')
 wrapper.unmount()
})
it('does not let an earlier manual refresh overwrite a later snapshot', async () => {
 const { wrapper } = await setup()
 let resolve!: (value: never) => void
 vi.mocked(fetchInterview).mockImplementationOnce(() => new Promise(done => { resolve = done }))
 await button(wrapper, '刷新进度').trigger('click')
 vi.mocked(fetchInterview).mockResolvedValueOnce({ ...initial(), currentTurn: 2, lastSeq: 3, turns: [{ ...question, turnIndex: 2, question: '新一轮问题' }] } as never)
 await vi.advanceTimersByTimeAsync(1500); await flushPromises()
 expect(wrapper.text()).toContain('新一轮问题')
 resolve(initial() as never); await flushPromises()
 expect(wrapper.text()).toContain('新一轮问题')
 wrapper.unmount()
})

it('stops promising another question once deleted memory invalidates a running practice', async () => {
 vi.mocked(fetchInterview).mockResolvedValue({ ...initial(), turns: [{ ...question, answer: '用一个事务保存回答' }], generation: { runId: 'run-2', status: 'running', cancelRequested: false, errorCode: null } } as never)
 const { wrapper } = await setup()
 expect(wrapper.text()).toContain('正在整理反馈与下一题')
 vi.mocked(fetchInterview).mockResolvedValue({ ...initial(), sessionInvalidated: true, turns: [{ ...question, answer: '用一个事务保存回答' }], generation: { runId: 'run-2', status: 'running', cancelRequested: true, errorCode: null } } as never)
 await vi.advanceTimersByTimeAsync(1500); await flushPromises()
 expect(wrapper.text()).toContain('这次练习使用的记忆已删除')
 expect(wrapper.text()).not.toContain('正在整理反馈与下一题')
 expect(button(wrapper, '重试生成')).toBeUndefined()
 expect(wrapper.text()).toContain('用一个事务保存回答')
 wrapper.unmount()
})

it.each(['before', 'after'])('keeps a confirmed memory when an older refresh finishes %s confirmation', async (order) => {
 const finished = { ...initial(), status: 'finished', turns: [{ ...question, answer: '单事务', feedback: {
  summary: '思路清楚', strengths: [], improvements: [], practiceFocus: '解释事务边界。',
 } }] }
 vi.mocked(fetchInterview).mockResolvedValue(structuredClone(finished) as never)
 let save!: (value: never) => void, refresh!: (value: never) => void
 vi.mocked(confirmInterviewMemory).mockImplementationOnce(() => new Promise(done => { save = done }))
 const { wrapper } = await setup()
 await button(wrapper, '保存练习要点').trigger('click')
 await button(wrapper, '确认保存记忆').trigger('click'); await flushPromises()
 vi.mocked(fetchInterview).mockImplementationOnce(() => new Promise(done => { refresh = done }))
 await button(wrapper, '刷新进度').trigger('click'); await flushPromises()
 if (order === 'before') { refresh(structuredClone(finished) as never); await flushPromises() }
 save({ id: 'saved-memory' } as never); await flushPromises()
 if (order === 'after') { refresh(structuredClone(finished) as never); await flushPromises() }
 expect(wrapper.text()).toContain('已保存练习记忆')
 expect(button(wrapper, '保存练习要点')).toBeUndefined()
 expect(confirmInterviewMemory).toHaveBeenCalledTimes(1)
 wrapper.unmount()
})

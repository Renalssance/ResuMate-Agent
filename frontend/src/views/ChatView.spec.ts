import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ChatView from './ChatView.vue'
import { useAuthStore } from '../stores/auth'
import { useDocumentStore } from '../stores/document'
import type { RunSnapshot, RunSubscriptionOptions } from '../services/agentStream'
import type { BackendDocumentParseResult } from '../api/documents'

const streams = vi.hoisted(() => [] as RunSubscriptionOptions[])
vi.mock('../services/agentStream', () => ({ subscribeRun: (options: RunSubscriptionOptions) => { streams.push(options); return { close: vi.fn(), done: new Promise(() => {}) } } }))
vi.mock('../api/documents', () => ({ fetchDocumentsApi: async () => documentResponse || [
  { id: 'resume:3', type: 'resume', filename: '我的简历.pdf', size: 10, raw_text: '', parsed_content: {}, vectorized: false, local_stored: true, parse_status: 'success', created_at: '2026-10-30' },
  { id: 'jd:4', type: 'jd', filename: '产品经理.txt', size: 10, raw_text: '', parsed_content: {}, vectorized: false, local_stored: true, parse_status: 'success', created_at: '2026-10-30' },
] }))
const session = { sessionId: 'session-1', title: '准备面试', createdAt: '2026-10-30', updatedAt: '2026-10-30', activeRunId: null }
const activeTurn = { runId: 'run-1', message: '帮我分析', status: 'running', text: '已经开始', lastSeq: 7, tools: [], outputRefs: [], result: null, errorCode: null }
let requests: { url: string; body: Record<string, unknown> }[]
let failSend = false
let cancelResponse: Promise<Response> | undefined
let nextDetailResponse: Promise<Response> | undefined
let detail: Record<string, unknown>
let importResponse: Promise<Response> | undefined
let importSnapshot: RunSnapshot
let documentResponse: Promise<BackendDocumentParseResult[]> | undefined
beforeEach(() => {
  sessionStorage.clear(); importResponse = undefined; documentResponse = undefined
  importSnapshot = { runId: 'import-1', sessionId: 'internal-session', sessionInvalidated: false,
    kind: 'document_import', status: 'queued', input: { filename: '新材料.txt' }, inputVersions: {},
    attempt: 1, lastSeq: 1, errorCode: null, cancelRequested: false, outputRefs: [], actions: [] }
  setActivePinia(createPinia()); useAuthStore().token = 'test'; streams.length = 0; requests = []; failSend = false; cancelResponse = undefined; nextDetailResponse = undefined
  detail = { ...session, turns: [] }
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    if (String(input).endsWith('/documents/import')) return importResponse || Response.json({ runId: 'import-1', status: 'queued' })
    const url = String(input), body = init?.body ? (init.body instanceof FormData ? Object.fromEntries(init.body.entries()) : JSON.parse(String(init.body))) : undefined
    if (body) requests.push({ url, body })
    if (url.endsWith('/actions/type-1')) return Response.json({ runId: 'import-1', status: 'queued' })
    if (url.endsWith('/runs/import-1')) return Response.json(importSnapshot)
    if (url.endsWith('/cancel')) return cancelResponse || Response.json({ runId: 'run-1', status: 'cancelled' })
    if ((url.endsWith('/messages') || url.endsWith('/messages/upload'))) return Response.json(failSend ? { message: '当前会话忙，请稍后重试' } : { runId: 'run-2', status: 'queued' }, { status: failSend ? 409 : 202 })
    if (url.endsWith('/sessions')) return Response.json(init?.method === 'POST' ? session : [session])
    if (nextDetailResponse) { const pending = nextDetailResponse; nextDetailResponse = undefined; return pending }
    return Response.json(detail)
  }))
})
afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear() })
async function open(path = '/chat') {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/chat/:sessionId?', component: ChatView }, { path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
  await router.push(path); await router.isReady()
  const wrapper = mount(ChatView, { global: { plugins: [router] } }); await flushPromises()
  return { wrapper, router }
}
describe('chat workspace', () => {
  it('shows live attachment analysis, restores its history and folds only when parsing completes', async () => {
    const first = { stage: 'extract', message: '已读取 1/3 页', current: 1, total: 3, createdAt: new Date().toISOString(), data: { scope: 'attachment', reset: true } }
    detail = { ...session, turns: [{ ...activeTurn, input: { attachment: { filename: '简历.pdf' } }, attachmentProgress: [first] }] }
    const { wrapper } = await open('/chat/session-1')
    expect(wrapper.get('.attachment-progress').text()).toContain('1/3')
    const stream = streams[0]!
    stream.onEvent({ runId: 'run-1', seq: 8, type: 'task.progress', createdAt: first.createdAt,
      payload: { stage: 'llm_analyze', message: '正在提取教育背景、经历和技能', data: { scope: 'attachment', kind: 'resume', agent: { phase: 'waiting_response', attempt: 1 } } } })
    await flushPromises()
    expect(wrapper.get('.attachment-progress').attributes('open')).toBeDefined()
    expect(wrapper.get('.attachment-progress').text()).toContain('正在提取教育背景、经历和技能')
    expect(wrapper.get('.attachment-progress').text()).toContain('分析过程')
    stream.onEvent({ runId: 'run-1', seq: 9, type: 'task.progress', createdAt: first.createdAt,
      payload: { stage: 'complete', message: '已保存到资料库', data: { scope: 'attachment', kind: 'resume' } } })
    await flushPromises()
    expect(wrapper.get('.attachment-progress').attributes('open')).toBeUndefined()
    expect(wrapper.get('.attachment-progress summary').text()).toContain('解析完成')
    expect(wrapper.get('.attachment-progress').find('.execution-spinner').exists()).toBe(false)
    expect(wrapper.find('.stop-button').exists()).toBe(true) // the chat answer is still running
    wrapper.unmount()
  })

  it.each(['failed', 'cancelled'])('stops attachment progress when the chat is %s', async status => {
    const progress = { stage: 'llm_analyze', message: '正在提取经历和技能', createdAt: new Date().toISOString(), data: { scope: 'attachment' } }
    detail = { ...session, turns: [{ ...activeTurn, status, input: { attachment: { filename: '简历.pdf' } }, attachmentProgress: [progress] }] }
    const { wrapper } = await open('/chat/session-1')
    expect(wrapper.get('.attachment-progress').find('.execution-spinner').exists()).toBe(false)
    expect(wrapper.get('.attachment-progress summary').text()).toContain(status === 'failed' ? '解析未完成' : '解析已停止')
    wrapper.unmount()
  })

  it('streams reasoning separately and folds it when the thinking phase ends', async () => {
    detail = { ...session, turns: [activeTurn] }
    const { wrapper } = await open('/chat/session-1')
    const stream = streams[0]!
    stream.onEvent({ runId: 'run-1', seq: 8, type: 'assistant.reasoning', createdAt: '', payload: { text: '先看岗位分布' } })
    await flushPromises()
    expect(wrapper.get('.reasoning-panel').attributes('open')).toBeDefined()
    expect(wrapper.get('.reasoning-content').text()).toBe('先看岗位分布')
    expect(wrapper.get('.assistant-text').text()).not.toContain('先看岗位分布')
    stream.onEvent({ runId: 'run-1', seq: 9, type: 'assistant.reasoning.done', createdAt: '', payload: {} })
    await flushPromises()
    expect(wrapper.get('.reasoning-panel').attributes('open')).toBeUndefined()
    stream.onEvent({ runId: 'run-1', seq: 10, type: 'assistant.reasoning', createdAt: '', payload: { text: '再看公司分布' } })
    await flushPromises()
    expect(wrapper.get('.reasoning-panel').attributes('open')).toBeDefined()
    expect(wrapper.get('.reasoning-content').text()).toBe('先看岗位分布\n\n再看公司分布')
    stream.onEvent({ runId: 'run-1', seq: 11, type: 'run.status', createdAt: '', payload: { status: 'failed' } })
    await flushPromises()
    expect(wrapper.get('.reasoning-panel').attributes('open')).toBeUndefined()
    expect(wrapper.get('.reasoning-content').text()).toContain('再看公司分布')
    wrapper.unmount()
  })
  it('keeps Milo welcoming after a rejected send and hands off to the reply only after acceptance', async () => {
    const { wrapper, router } = await open()
    const mascot = wrapper.get('.welcome-milo img').attributes('src')
    await wrapper.get('textarea').setValue('帮我看看项目经历')
    failSend = true
    await wrapper.get('form.chat-composer').trigger('submit'); await flushPromises()
    expect(wrapper.find('.welcome-milo').exists()).toBe(true)
    expect(wrapper.find('.assistant-avatar').exists()).toBe(false)
    failSend = false
    await wrapper.get('form.chat-composer').trigger('submit'); await flushPromises()
    expect(wrapper.find('.welcome-milo').exists()).toBe(false)
    expect(wrapper.get('.assistant-avatar img').attributes('src')).toBe(mascot)
    expect(wrapper.text()).toContain('等待回复')
    await router.push('/chat'); await flushPromises()
    expect(wrapper.find('.welcome-milo').exists()).toBe(true)
    expect(wrapper.find('.assistant-avatar').exists()).toBe(false)
    wrapper.unmount()
  })
  it('sends materials selected through the picker and displays the accepted queued turn', async () => {
    const { wrapper } = await open()
    await wrapper.get('[aria-label="添加材料"]').trigger('click')
    await wrapper.get('[data-source="resume"]').trigger('click')
    await wrapper.get('[data-resume-id="resume:3"]').trigger('click')
    await wrapper.get('[aria-label="添加材料"]').trigger('click')
    await wrapper.get('[data-source="job"]').trigger('click')
    await wrapper.get('[data-job-id="jd:4"]').trigger('click')
    await wrapper.get('textarea').setValue('帮我准备这份岗位')
    await wrapper.get('form.chat-composer').trigger('submit'); await flushPromises()
    const sent = requests.find(item => item.url.endsWith('/messages'))!
    expect(sent.body).toMatchObject({ message: '帮我准备这份岗位', resumeId: 3, jdId: 4 })
    expect(typeof sent.body.requestId).toBe('string')
    expect(wrapper.text()).toContain('帮我准备这份岗位')
    expect(wrapper.text()).toContain('等待回复')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('')
    wrapper.unmount()
  })
  it('preserves the message when the server rejects it', async () => {
    failSend = true
    const { wrapper } = await open('/chat/session-1')
    await wrapper.get('textarea').setValue('不要丢失这条消息')
    await wrapper.get('form.chat-composer').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('当前会话忙')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('不要丢失这条消息')
    const firstRequestId = requests.find(item => item.url.endsWith('/messages'))!.body.requestId
    failSend = false
    await wrapper.get('form.chat-composer').trigger('submit'); await flushPromises()
    expect(requests.filter(item => item.url.endsWith('/messages'))[1]!.body.requestId).toBe(firstRequestId)
    expect(wrapper.text()).toContain('等待回复')
    wrapper.unmount()
  })
  it('unlocks the composer after switching sessions while a stop request is pending', async () => {
    detail = { ...session, activeRunId: 'run-1', turns: [activeTurn] }
    let finishCancel!: () => void
    cancelResponse = new Promise(resolve => { finishCancel = () => resolve(Response.json({ runId: 'run-1', status: 'cancelled' })) })
    const { wrapper, router } = await open('/chat/session-1')
    await wrapper.get('.stop-button').trigger('click')
    detail = { ...session, sessionId: 'session-2', turns: [] }
    await router.push('/chat/session-2'); await flushPromises()
    finishCancel(); await flushPromises()
    await wrapper.get('textarea').setValue('继续新会话')
    expect(wrapper.get('[aria-label="发送消息"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('.history-heading button').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
  it('keeps a newly accepted turn when an older history response arrives', async () => {
    detail = { ...session, activeRunId: 'run-1', turns: [activeTurn] }
    const { wrapper } = await open('/chat/session-1')
    let finishHistory!: () => void
    nextDetailResponse = new Promise(resolve => { finishHistory = () => resolve(Response.json({ ...session,
      turns: [{ ...activeTurn, status: 'succeeded', text: '第一轮结束', lastSeq: 8, result: { text: '第一轮结束' } }] })) })
    streams.find(item => item.runId === 'run-1')!.onEvent({ runId: 'run-1', seq: 8, type: 'run.status', createdAt: '', payload: { status: 'succeeded' } })
    await wrapper.get('textarea').setValue('接着准备面试')
    await wrapper.get('form.chat-composer').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('接着准备面试')
    finishHistory(); await flushPromises()
    expect(wrapper.text()).toContain('接着准备面试')
    expect(wrapper.find('.stop-button').exists()).toBe(true)
    vi.useFakeTimers()
    try {
      streams.find(item => item.runId === 'run-2')!.onEvent({ runId: 'run-2', seq: 1, type: 'assistant.delta', createdAt: '', payload: { text: '第二轮继续' } })
      await flushPromises()
      await vi.advanceTimersByTimeAsync(144)
      expect(wrapper.text()).toContain('第二轮继续')
    } finally { vi.useRealTimers() }
    wrapper.unmount()
  })
  it('stages a local file without uploading and sends it with the question', async () => {
    const { wrapper } = await open()
    await wrapper.get('[aria-label="添加材料"]').trigger('click')
    const input = wrapper.get('input[type="file"]')
    const file = new File(['content'], '新材料.txt')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change'); await flushPromises()
    expect(wrapper.get('.pending-attachment').text()).toContain('新材料.txt')
    expect(requests).toHaveLength(0)
    expect(streams).toHaveLength(0)
    await wrapper.get('textarea').setValue('总结文件')
    await wrapper.get('form.chat-composer').trigger('submit'); await flushPromises()
    const request = requests.find(item => item.url.endsWith('/messages/upload'))!
    expect(request.body.message).toBe('总结文件')
    expect(request.body.file).toBe(file)
    expect(wrapper.find('.pending-attachment').exists()).toBe(false)
    expect(wrapper.get('.user-message').text()).toContain('新材料.txt')
    wrapper.unmount()
  })
  it('can remove a staged file and retains it after a rejected send', async () => {
    const { wrapper } = await open()
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [new File(['notes'], 'notes.txt')] })
    await input.trigger('change')
    await wrapper.get('[aria-label="移除附件"]').trigger('click')
    expect(wrapper.find('.pending-attachment').exists()).toBe(false)
    await input.trigger('change')
    await wrapper.get('textarea').setValue('总结')
    failSend = true
    await wrapper.get('form.chat-composer').trigger('submit'); await flushPromises()
    expect(wrapper.get('.pending-attachment').text()).toContain('notes.txt')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('总结')
    wrapper.unmount()
  })
  it('refreshes library choices after an attachment reply completes', async () => {
    detail = { ...session, turns: [{ ...activeTurn, input: { attachment: { filename: '新简历.txt' } } }] }
    const { wrapper } = await open('/chat/session-1')
    documentResponse = Promise.resolve([{
      id: 'resume:9', type: 'resume', filename: '新简历.txt', size: 12, raw_text: 'content',
      parsed_content: {}, vectorized: false, local_stored: true, parse_status: 'success', created_at: '2026-10-31',
    }])
    detail = { ...session, turns: [{ ...activeTurn, status: 'succeeded', input: { attachment: { filename: '新简历.txt' } } }] }
    streams.find(stream => stream.runId === 'run-1')!.onEvent({ runId: 'run-1', seq: 8, type: 'run.status', createdAt: '', payload: { status: 'succeeded' } })
    await flushPromises()
    expect(useDocumentStore().parsedResumes.map(doc => doc.id)).toContain('resume:9')
    wrapper.unmount()
  })
  it('resumes from the saved sequence and reloads canonical text after completion', async () => {
    detail = { ...session, activeRunId: 'run-1', turns: [activeTurn] }
    const { wrapper } = await open('/chat/session-1')
    const stream = streams.find(item => item.runId === 'run-1')!
    expect(stream.after).toBe(7)
    expect(wrapper.text()).toContain('已经开始')
    vi.useFakeTimers()
    try {
      stream.onEvent({ runId: 'run-1', seq: 8, type: 'assistant.delta', createdAt: '', payload: { text: '，继续分析' } })
      await flushPromises(); await vi.advanceTimersByTimeAsync(120)
      expect(wrapper.text()).toContain('已经开始，继续分析')
    } finally { vi.useRealTimers() }
    detail = { ...session, turns: [{ ...activeTurn, status: 'succeeded', text: '最终分析结果', result: { text: '最终分析结果' }, lastSeq: 9 }] }
    stream.onEvent({ runId: 'run-1', seq: 9, type: 'run.status', createdAt: '', payload: { status: 'succeeded' } })
    await flushPromises()
    expect(wrapper.text()).toContain('最终分析结果')
    expect(wrapper.text()).not.toContain('已经开始，继续分析')
    wrapper.unmount()
  })
  it('shows tool progress before the final answer and collapses it when the answer is ready', async () => {
    detail = { ...session, turns: [{ ...activeTurn, status: 'succeeded', text: '处理中', tools: [
      { name: 'list_documents', operationKey: 'tool-1', status: 'succeeded', resultRef: null },
      { name: 'read_document', operationKey: 'tool-2', status: 'succeeded', resultRef: null },
    ], result: { text: '这是最终岗位建议' } }] }
    const { wrapper } = await open('/chat/session-1')
    const progress = wrapper.get('.chat-process')
    const answer = wrapper.get('.assistant-text')
    expect(progress.attributes('open')).toBeUndefined()
    expect(progress.text()).toContain('查看文档')
    expect(progress.element.compareDocumentPosition(answer.element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(answer.text()).toBe('这是最终岗位建议')
    wrapper.unmount()
  })
  it('keeps tool progress expanded while the answer is still running', async () => {
    detail = { ...session, activeRunId: 'run-1', turns: [{ ...activeTurn, tools: [
      { name: 'read_document', operationKey: 'tool-1', status: 'running', resultRef: null },
    ] }] }
    const { wrapper } = await open('/chat/session-1')
    expect(wrapper.get('.chat-process').attributes('open')).toBeDefined()
    expect(wrapper.find('.chat-tools .execution-spinner').exists()).toBe(true)
    expect(wrapper.find('.assistant-label .execution-spinner').exists()).toBe(true)
    detail = { ...session, turns: [{ ...activeTurn, status: 'failed', lastSeq: 8, errorCode: 'empty_response' }] }
    streams[0]!.onEvent({ runId: 'run-1', seq: 8, type: 'run.status', createdAt: '', payload: { status: 'failed' } })
    await flushPromises()
    expect(wrapper.find('.execution-spinner').exists()).toBe(false)
    expect(wrapper.get('.chat-failure').text()).toContain('模型未生成有效回复')
    wrapper.unmount()
  })
  it('renders assistant markdown as structured content', async () => {
    detail = { ...session, turns: [{ ...activeTurn, status: 'succeeded', text: '', result: {
      text: '## 岗位建议\n\n- **优先**：算法测试\n- Agent 工程',
    } }] }
    const { wrapper } = await open('/chat/session-1')
    expect(wrapper.get('.assistant-text h2').text()).toBe('岗位建议')
    expect(wrapper.findAll('.assistant-text li')).toHaveLength(2)
    expect(wrapper.get('.assistant-text strong').text()).toBe('优先')
    expect(wrapper.find('[aria-label="复制米洛的回复"]').exists()).toBe(true)
    await wrapper.get('.reply-suggestions button').trigger('click')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('请根据刚才的建议，帮我改写这段经历')
    expect(requests.filter(request => request.url.endsWith('/messages'))).toHaveLength(0)
    wrapper.unmount()
  })
  it('smooths a small streamed chunk and highlights the newest visible character', async () => {
    detail = { ...session, activeRunId: 'run-1', turns: [{ ...activeTurn, text: '' }] }
    const { wrapper } = await open('/chat/session-1')
    const stream = streams.find(item => item.runId === 'run-1')!
    vi.useFakeTimers()
    try {
      stream.onEvent({ runId: 'run-1', seq: 8, type: 'assistant.delta', createdAt: '', payload: { text: '岗位' } })
      await flushPromises()
      expect(wrapper.get('.assistant-text').text()).toBe('')
      await vi.advanceTimersByTimeAsync(64)
      expect(wrapper.get('.assistant-text').text()).toBe('岗')
      expect(wrapper.get('.stream-char').text()).toBe('岗')
      await vi.advanceTimersByTimeAsync(64)
      expect(wrapper.get('.assistant-text').text()).toBe('岗位')
    } finally {
      vi.useRealTimers()
      wrapper.unmount()
    }
  })
  it('starts the message composer as a single-line control', async () => {
    const { wrapper } = await open('/chat/session-1')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).rows).toBe(1)
    wrapper.unmount()
  })
  it.each([
    { isComposing: true, keyCode: 13 },
    { isComposing: false, keyCode: 229 },
  ])('does not send the Enter used to commit IME text (%j)', async (imeEvent) => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })))
    const { wrapper } = await open()
    const field = wrapper.get('textarea')
    await field.setValue('resumate')
    const confirmation = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true, ...imeEvent })
    field.element.dispatchEvent(confirmation)
    await flushPromises()
    expect(confirmation.defaultPrevented).toBe(false)
    expect(requests).toHaveLength(0)
    expect((field.element as HTMLTextAreaElement).value).toBe('resumate')
    await field.trigger('keydown', { key: 'Enter', shiftKey: true })
    await flushPromises()
    expect(requests).toHaveLength(0)
    await field.trigger('keydown', { key: 'Enter', keyCode: 13, isComposing: false })
    await flushPromises()
    expect(requests.filter(request => request.url.endsWith('/messages'))).toHaveLength(1)
    wrapper.unmount()
  })
})

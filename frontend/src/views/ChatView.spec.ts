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
    const url = String(input), body = init?.body ? JSON.parse(String(init.body)) : undefined
    if (body) requests.push({ url, body })
    if (url.endsWith('/actions/type-1')) return Response.json({ runId: 'import-1', status: 'queued' })
    if (url.endsWith('/runs/import-1')) return Response.json(importSnapshot)
    if (url.endsWith('/cancel')) return cancelResponse || Response.json({ runId: 'run-1', status: 'cancelled' })
    if (url.endsWith('/messages')) return Response.json(failSend ? { message: '当前会话忙，请稍后重试' } : { runId: 'run-2', status: 'queued' }, { status: failSend ? 409 : 202 })
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
  it('restores each conversation material selection when switching sessions', async () => {
    sessionStorage.setItem('resumate:document-import:chat:session-1', 'import-1')
    importSnapshot = { ...importSnapshot, status: 'waiting_input', actions: [{ actionId: 'type-1', kind: 'input', revision: 1,
      payload: { reason: '请确认这份材料的类型', choices: [{ value: 'resume', label: '简历' }, { value: 'jd', label: '岗位' }] } }] }
    detail = { ...session, turns: [{ ...activeTurn, status: 'succeeded', input: { resumeId: 3, jdId: 4 } }] }
    const { wrapper, router } = await open('/chat/session-1')
    expect(wrapper.get('.material-chip[title="我的简历.pdf"]').text()).toContain('我的简历.pdf')
    expect(wrapper.get('.material-chip[title="产品经理.txt"]').text()).toContain('产品经理.txt')
    expect(wrapper.text()).toContain('请确认这份材料的类型')
    detail = { ...session, sessionId: 'session-2', turns: [] }
    await router.push('/chat/session-2'); await flushPromises()
    expect(wrapper.findAll('.material-chip')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('请确认这份材料的类型')
    importSnapshot = { ...importSnapshot, status: 'succeeded', lastSeq: 4, actions: [], result: { documents: [{
      id: 'resume:8', type: 'resume', filename: '新材料.txt', size: 10, raw_text: 'content', parsed_content: {},
      vectorized: false, local_stored: true, parse_status: 'success', created_at: '2026-10-31',
    }] } }
    let finishHistory!: () => void
    nextDetailResponse = new Promise(resolve => { finishHistory = () => resolve(Response.json({ ...session,
      turns: [{ ...activeTurn, status: 'succeeded', input: { resumeId: 3, jdId: 4 } }] })) })
    await router.push('/chat/session-1'); await flushPromises()
    finishHistory(); await flushPromises()
    expect(wrapper.get('.material-chip[title="新材料.txt"]').text()).toContain('新材料.txt')
    expect(wrapper.get('.material-chip[title="产品经理.txt"]').text()).toContain('产品经理.txt')
    wrapper.unmount()
  })
  it.each([
    { type: 'resume', id: 'resume:8', context: { resumeId: 8 }, confirm: false },
    { type: 'jd', id: 'jd:9', context: { jdId: 9 }, confirm: true },
  ])('adopts an imported $type before sending its real ID as context', async ({ type, id, context, confirm }) => {
    let acceptImport!: () => void
    importResponse = new Promise(resolve => { acceptImport = () => resolve(Response.json({ runId: 'import-1', status: 'queued' })) })
    const { wrapper, router } = await open()
    await wrapper.get('[aria-label="添加材料"]').trigger('click')
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [new File(['content'], '新材料.txt')] })
    await input.trigger('change'); await flushPromises()
    await wrapper.get('textarea').setValue('分析我刚上传的材料')
    expect(wrapper.get('[aria-label="发送消息"]').attributes('disabled')).toBeDefined()
    await wrapper.get('form.chat-composer').trigger('submit'); await flushPromises()
    expect(router.currentRoute.value.path).toBe('/chat')
    expect(requests).toHaveLength(0)
    acceptImport(); await flushPromises()
    expect(wrapper.get('[aria-label="发送消息"]').attributes('disabled')).toBeDefined()
    await wrapper.get('form.chat-composer').trigger('submit'); await flushPromises()
    expect(requests).toHaveLength(0)
    const stream = streams.find(item => item.runId === 'import-1')!
    if (confirm) {
      stream.onSnapshot?.({ ...importSnapshot, status: 'waiting_input', actions: [{ actionId: 'type-1', kind: 'input', revision: 1,
        payload: { reason: '请确认这份材料的类型', choices: [{ value: 'resume', label: '简历' }, { value: 'jd', label: '岗位' }] } }] })
      await flushPromises()
      expect(wrapper.get('[aria-label="发送消息"]').attributes('disabled')).toBeDefined()
      await wrapper.get('form.chat-composer').trigger('submit'); await flushPromises()
      expect(router.currentRoute.value.path).toBe('/chat')
      expect(requests).toHaveLength(0)
      expect(sessionStorage.getItem('resumate:document-import:chat:new')).toBe('import-1')
      await wrapper.get('[data-document-type="jd"]').trigger('click'); await flushPromises()
      expect(requests.find(item => item.url.endsWith('/actions/type-1'))!.body).toMatchObject({ answers: { documentType: 'jd' } })
    }
    stream.onSnapshot?.({ ...importSnapshot, status: 'succeeded', lastSeq: 4, result: { documents: [{
      id, type, filename: '新材料.txt', size: 10, raw_text: 'content', parsed_content: { title: 'API 工程师' },
      vectorized: false, local_stored: true, parse_status: 'success', created_at: '2026-10-31',
    }] } })
    await flushPromises()
    expect(wrapper.get('.material-chip[title="新材料.txt"]').text()).toContain('新材料.txt')
    expect(useDocumentStore().documents.find(item => item.id === id)).toMatchObject({ parseStatus: 'success', parsedContent: { title: 'API 工程师' } })
    await wrapper.get('form.chat-composer').trigger('submit'); await flushPromises()
    expect(requests.find(item => item.url.endsWith('/messages'))!.body).toMatchObject(context)
    wrapper.unmount()
  })
  it('adopts a recovered import after the older document list has finished loading', async () => {
    sessionStorage.setItem('resumate:document-import:chat:session-1', 'import-1')
    importSnapshot = { ...importSnapshot, status: 'succeeded', lastSeq: 4, result: { documents: [{
      id: 'resume:8', type: 'resume', filename: '新材料.txt', size: 10, raw_text: 'content', parsed_content: {},
      vectorized: false, local_stored: true, parse_status: 'success', created_at: '2026-10-31',
    }] } }
    let finishList!: (documents: BackendDocumentParseResult[]) => void
    documentResponse = new Promise(resolve => { finishList = resolve })
    const { wrapper } = await open('/chat/session-1')
    finishList([]); await flushPromises()
    expect(wrapper.get('.material-chip[title="新材料.txt"]').text()).toContain('新材料.txt')
    expect(useDocumentStore().parsedResumes.map(doc => doc.id)).toEqual(['resume:8'])
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
    wrapper.unmount()
  })
  it('reveals a streaming reply one character at a time', async () => {
    detail = { ...session, activeRunId: 'run-1', turns: [{ ...activeTurn, text: '' }] }
    const { wrapper } = await open('/chat/session-1')
    const stream = streams.find(item => item.runId === 'run-1')!
    vi.useFakeTimers()
    try {
      stream.onEvent({ runId: 'run-1', seq: 8, type: 'assistant.delta', createdAt: '', payload: { text: '岗位' } })
      await flushPromises()
      expect(wrapper.get('.assistant-text').text()).toBe('')
      await vi.advanceTimersByTimeAsync(24)
      expect(wrapper.get('.assistant-text').text()).toBe('岗')
      expect(wrapper.get('.stream-char').text()).toBe('岗')
      await vi.advanceTimersByTimeAsync(24)
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
})

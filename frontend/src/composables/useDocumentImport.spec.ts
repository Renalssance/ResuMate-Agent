import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, ref } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { answerRunAction, fetchAgentRun } from '../api/agentRuns'
import type { RunSnapshot, RunSubscriptionOptions } from '../services/agentStream'
import { useDocumentImport } from './useDocumentImport'

vi.mock('../api/agentRuns', () => ({ fetchAgentRun: vi.fn(), answerRunAction: vi.fn() }))
const streams = vi.hoisted(() => [] as (RunSubscriptionOptions & { close: ReturnType<typeof vi.fn> })[])
vi.mock('../services/agentStream', () => ({
  subscribeRun: (options: RunSubscriptionOptions) => {
    const stream = { ...options, close: vi.fn() }
    streams.push(stream)
    return { close: stream.close, done: Promise.resolve() }
  },
}))

const key = 'resumate:document-import:chat:session-1'
const document = {
  id: 'resume:7', type: 'resume', filename: 'neutral.txt', size: 7,
  raw_text: 'content', parsed_content: { name: 'Candidate' }, vectorized: true,
  local_stored: true, parse_status: 'success', created_at: '2026-10-31T00:00:00Z',
}
const queued: RunSnapshot = {
  runId: 'import-1', sessionId: 'internal-session', sessionInvalidated: false,
  kind: 'document_import', status: 'queued', input: { filename: 'neutral.txt' },
  inputVersions: {}, attempt: 1, lastSeq: 1, errorCode: null,
  cancelRequested: false, outputRefs: [], actions: [],
}
const waiting: RunSnapshot = {
  ...queued, status: 'waiting_input', lastSeq: 3,
  actions: [{ actionId: 'action-1', kind: 'input', revision: 1, payload: {
    question: '这份文件属于哪一类？', reason: '内容不足以区分', filename: 'neutral.txt',
    choices: [{ value: 'resume', label: '简历' }, { value: 'jd', label: '岗位' }],
  } }],
}
let wrapper: VueWrapper | undefined
function openChat(scope = ref('chat:session-1')) {
  let flow!: ReturnType<typeof useDocumentImport>
  wrapper = mount(defineComponent({
    setup() { flow = useDocumentImport(scope); return () => null },
  }))
  return flow
}

beforeEach(() => {
  streams.length = 0
  sessionStorage.clear()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true, json: async () => ({ runId: 'import-1', status: 'queued' }),
  }))
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.unstubAllGlobals(); sessionStorage.clear() })

it('uploads with a UUID request ID when randomUUID is unavailable', async () => {
  vi.stubGlobal('crypto', { getRandomValues: crypto.getRandomValues.bind(crypto) })
  const flow = openChat()
  await flow.startImport(new File(['content'], 'neutral.txt'))
  expect(flow.error.value).toBe('')
  expect(fetch).toHaveBeenCalledOnce()
  const request = vi.mocked(fetch).mock.calls[0]![1]!
  expect((request.body as FormData).get('requestId')).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  )
  expect(flow.state.value).toBe('processing')
})

it('returns the parsed document when the import run succeeds', async () => {
  const flow = openChat()
  const file = new File(['content'], 'neutral.txt')
  await flow.startImport(file)
  const [url, request] = vi.mocked(fetch).mock.calls[0]!
  expect(url).toBe('/api/documents/import')
  expect((request!.body as FormData).get('file')).toBe(file)
  expect((request!.body as FormData).get('requestId')).toEqual(expect.any(String))
  expect(sessionStorage.getItem(key)).toBe('import-1')
  streams[0]!.onSnapshot?.(queued)
  vi.mocked(fetchAgentRun).mockResolvedValue({
    ...queued, status: 'succeeded', lastSeq: 4, result: { documents: [document] },
  })
  streams[0]!.onEvent({ runId: 'import-1', seq: 4, createdAt: '', type: 'run.status', payload: { status: 'succeeded' } })
  await flushPromises()
  expect(flow.state.value).toBe('succeeded')
  expect(flow.resultDocument.value).toMatchObject({
    id: 'resume:7', type: 'resume', rawText: 'content', parsedContent: { name: 'Candidate' },
    parseStatus: 'success', createdAt: '2026-10-31T00:00:00Z', localStored: true,
  })
  expect(sessionStorage.getItem(key)).toBeNull()
})

it('exposes document type choices and answers the existing run action', async () => {
  const flow = openChat()
  await flow.startImport(new File(['content'], 'neutral.txt'))
  streams[0]!.onSnapshot?.(waiting)
  expect(flow.state.value).toBe('waiting_input')
  expect(flow.pendingAction.value?.payload.choices).toEqual([
    { value: 'resume', label: '简历' }, { value: 'jd', label: '岗位' },
  ])
  await flow.startImport(new File(['replacement'], 'replacement.txt'))
  expect(flow.pendingAction.value?.actionId).toBe('action-1')
  expect(sessionStorage.getItem(key)).toBe('import-1')
  expect(vi.mocked(fetch).mock.calls).toHaveLength(1)
  vi.mocked(answerRunAction).mockResolvedValue({ runId: 'import-1', status: 'queued' })
  await flow.confirmDocumentType('jd')
  expect(answerRunAction).toHaveBeenCalledWith('import-1', 'action-1', {
    decision: 'submit', answers: { documentType: 'jd' }, expectedRevision: 1,
  })
  expect(flow.pendingAction.value).toBeNull()
  expect(flow.state.value).toBe('processing')
})

it('reconnects for the canonical result if the terminal event snapshot request fails', async () => {
  const flow = openChat()
  await flow.startImport(new File(['content'], 'neutral.txt'))
  streams[0]!.onSnapshot?.(queued)
  vi.mocked(fetchAgentRun).mockRejectedValueOnce(new TypeError('offline'))
  streams[0]!.onEvent({ runId: 'import-1', seq: 4, createdAt: '', type: 'run.status', payload: { status: 'succeeded' } })
  await flushPromises()
  expect(streams).toHaveLength(2)
  expect(sessionStorage.getItem(key)).toBe('import-1')
  streams[1]!.onSnapshot?.({ ...queued, status: 'succeeded', lastSeq: 4, result: { documents: [document] } })
  expect(flow.state.value).toBe('succeeded')
  expect(flow.resultDocument.value?.id).toBe('resume:7')
  expect(flow.error.value).toBe('')
})

it('retains recovery on close and restores the active import for its reactive chat scope', async () => {
  const scope = ref('chat:session-1')
  const first = openChat(scope)
  let acceptUpload!: (response: Response) => void
  vi.mocked(fetch).mockImplementationOnce(() => new Promise(resolve => { acceptUpload = resolve }))
  const superseded = first.startImport(new File(['old'], 'old.txt'))
  await first.startImport(new File(['content'], 'neutral.txt'))
  acceptUpload(Response.json({ runId: 'superseded-import', status: 'queued' }))
  await superseded
  expect(sessionStorage.getItem(key)).toBe('import-1')
  vi.mocked(fetch).mockImplementationOnce(() => new Promise(resolve => { acceptUpload = resolve }))
  const leaving = first.startImport(new File(['content'], 'neutral.txt'))
  scope.value = 'chat:session-2'
  vi.mocked(fetch).mockResolvedValueOnce(Response.json({ runId: 'import-in-chat-2', status: 'queued' }))
  await first.startImport(new File(['other'], 'other-chat.txt'))
  acceptUpload(Response.json({ runId: 'import-1', status: 'queued' }))
  await leaving
  await flushPromises()
  expect(streams[0]!.close).toHaveBeenCalledOnce()
  expect(first.state.value).toBe('processing')
  expect(sessionStorage.getItem(key)).toBe('import-1')
  expect(sessionStorage.getItem('resumate:document-import:chat:session-2')).toBe('import-in-chat-2')
  vi.mocked(fetchAgentRun).mockResolvedValue(waiting)
  scope.value = 'chat:session-1'
  await flushPromises()
  expect(first.state.value).toBe('waiting_input')
  expect(streams[2]!.runId).toBe('import-1')
  wrapper!.unmount()
  wrapper = undefined
  expect(streams[2]!.close).toHaveBeenCalledOnce()
  const recovered = openChat()
  await flushPromises()
  expect(recovered.pendingAction.value?.actionId).toBe('action-1')
  expect(streams[3]!.runId).toBe('import-1')
})

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAgentRunStore } from './agentRun'
import { useAuthStore } from './auth'
import * as api from '../api/agentRuns'
import { subscribeRun, type RunSnapshot, type RunSubscriptionOptions } from '../services/agentStream'
vi.mock('../api/agentRuns', () => ({ fetchAgentRuns: vi.fn(), fetchAgentRun: vi.fn(), fetchRunArtifacts: vi.fn(), createAgentRun: vi.fn(), answerRunAction: vi.fn(), cancelAgentRun: vi.fn(), retryAgentRun: vi.fn(), AgentRunError: class extends Error { constructor(public status: number, public code: string, message: string) { super(message) } } }))
vi.mock('../services/agentStream', () => ({ subscribeRun: vi.fn() }))
const action = { actionId: 'a1', kind: 'input' as const, payload: { question: '你负责什么工作？' }, revision: 1 }
const snapshot = (overrides: Partial<RunSnapshot> = {}): RunSnapshot => ({ runId: 'r1', sessionId: 's1', kind: 'tailoring', status: 'waiting_input', input: { jdId: 1, resumeId: 2 }, inputVersions: {}, attempt: 1, lastSeq: 4, errorCode: null, sessionInvalidated: false, cancelRequested: false, outputRefs: [], actions: [action], ...overrides })
let options: RunSubscriptionOptions
let close: ReturnType<typeof vi.fn<() => void>>
beforeEach(() => { vi.useFakeTimers(); setActivePinia(createPinia()); vi.resetAllMocks(); close = vi.fn(); vi.mocked(subscribeRun).mockImplementation((value) => { options = value; return { close, done: Promise.resolve() } }); vi.mocked(api.fetchRunArtifacts).mockResolvedValue([]); vi.mocked(api.fetchAgentRun).mockResolvedValue(snapshot()) })
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers() })
describe('persistent task workspace', () => {
  it('keeps the authoritative snapshot while replaying older statuses, and disconnect never fails a run', async () => {
    const store = useAgentRunStore(); store.openRun('r1'); options.onSnapshot?.(snapshot())
    options.onEvent({ runId: 'r1', seq: 1, createdAt: '', type: 'run.status', payload: { status: 'running' } }); options.onError?.(new TypeError('offline'))
    await vi.advanceTimersByTimeAsync(100)
    expect(store.snapshot?.status).toBe('waiting_input'); expect(store.disconnected).toBe(true); expect(store.events).toHaveLength(1)
  })
  it('ignores an old page response and closes the stream without cancelling the task', () => {
    const store = useAgentRunStore(); store.openRun('r1'); const old = options; store.openRun('r2'); old.onSnapshot?.(snapshot())
    expect(store.snapshot).toBeNull(); expect(close).toHaveBeenCalled(); expect(api.cancelAgentRun).not.toHaveBeenCalled()
  })
  it('preserves the answer on 409, refreshes pending actions, and explains the conflict', async () => {
    const store = useAgentRunStore(); store.openRun('r1'); options.onSnapshot?.(snapshot()); store.drafts.a1 = '负责 API 和数据库设计'
    vi.mocked(api.answerRunAction).mockRejectedValue(new api.AgentRunError(409, 'action_conflict', '该动作已提交不同回答')); vi.mocked(api.fetchAgentRun).mockResolvedValue(snapshot({ actions: [], status: 'running', lastSeq: 5 }))
    await store.submitAction(action)
    expect(store.drafts.a1).toBe('负责 API 和数据库设计'); expect(store.notice).toContain('已变化'); expect(store.snapshot?.actions).toEqual([]); expect(store.conflictedActions).toEqual([action])
  })
  it('clears a draft only after a successful submission', async () => {
    const store = useAgentRunStore(); store.openRun('r1'); options.onSnapshot?.(snapshot()); store.drafts.a1 = '职责'; vi.mocked(api.answerRunAction).mockResolvedValue({ runId: 'r1', status: 'queued' })
    await store.submitAction(action)
    expect(store.drafts.a1).toBeUndefined(); expect(store.notice).toBe('回答已提交'); expect(api.answerRunAction).toHaveBeenCalledWith('r1', 'a1', { decision: 'submit', answers: { answer: '职责' }, expectedRevision: 1 })
  })
  it('discards async detail responses after navigation and user logout clears all account data', async () => {
    const store = useAgentRunStore(); store.openRun('r1'); options.onSnapshot?.(snapshot()); store.drafts.a1 = '未提交';
    let resolve!: (value: RunSnapshot) => void; vi.mocked(api.fetchAgentRun).mockImplementationOnce(() => new Promise(done => { resolve = done }));
    const refresh = store.refresh(); store.openRun('r2'); resolve(snapshot()); await refresh; expect(store.snapshot).toBeNull();
    store.drafts.a1 = '另一个用户不应看到'; useAuthStore().token = 'new-user'; expect(store.drafts).toEqual({}); expect(store.runs).toEqual([]); expect(store.snapshot).toBeNull();
  })
  it('keeps completed artifacts when overlapping refresh responses finish in reverse order', async () => {
    const store = useAgentRunStore(); store.openRun('r1');
    let resolveOld!: (value: RunSnapshot) => void;
    const artifact = { id: 'material', runId: 'r1', resumeId: 2, jdId: 1, revision: 1, status: 'draft', structuredContent: { summary: '材料' }, factRefs: [], createdAt: '' };
    vi.mocked(api.fetchAgentRun).mockImplementationOnce(() => new Promise(done => { resolveOld = done })).mockResolvedValueOnce(snapshot({ status: 'succeeded', lastSeq: 10, actions: [] }));
    vi.mocked(api.fetchRunArtifacts).mockResolvedValueOnce([]).mockResolvedValueOnce([artifact]);
    const old = store.refresh(); await store.refresh(); resolveOld(snapshot({ lastSeq: 4 })); await old;
    expect(store.snapshot?.status).toBe('succeeded'); expect(store.artifacts).toEqual([artifact]);
  })
  it('accepts an idle reconnect snapshot without regressing to an older snapshot', () => {
    const store = useAgentRunStore(); store.openRun('r1'); options.onSnapshot?.(snapshot()); options.onError?.(new TypeError('offline'));
    options.onConnected?.(snapshot({ status: 'succeeded', lastSeq: 9, actions: [] })); expect(store.disconnected).toBe(false);
    options.onSnapshot?.(snapshot({ lastSeq: 4 })); expect(store.snapshot?.status).toBe('succeeded');
  })
  it('reuses the request ID when retrying the same create intent after a network error', async () => {
    const store = useAgentRunStore(); vi.mocked(api.createAgentRun).mockRejectedValueOnce(new TypeError('offline')).mockResolvedValueOnce({ runId: 'r1', status: 'queued' })
    await store.createRun('jd:1', 'resume:2'); await store.createRun('jd:1', 'resume:2')
    const calls = vi.mocked(api.createAgentRun).mock.calls; expect(calls[0][0]).toMatchObject({ jdId: 1, resumeId: 2 }); expect(calls[0][0].requestId).toBe(calls[1][0].requestId)
  })
})

it('refreshes an already open failed task when retry reports a session invalidated in another page', async () => {
 const store = useAgentRunStore(); store.openRun('r1'); store.snapshot = snapshot({ status: 'failed', errorCode: 'model_timeout', actions: [] })
 vi.mocked(api.retryAgentRun).mockRejectedValue(new api.AgentRunError(409, 'session_context_invalidated', '会话已失效'))
 vi.mocked(api.fetchAgentRun).mockResolvedValue(snapshot({ status: 'failed', errorCode: 'model_timeout', sessionInvalidated: true, actions: [] }))
 await store.changeRun('retry')
 expect(store.snapshot?.sessionInvalidated).toBe(true); expect(store.snapshot?.status).toBe('failed'); expect(store.snapshot?.errorCode).toBe('model_timeout'); expect(store.notice).toContain('旧会话不能恢复'); expect(store.notice).toContain('重新准备材料'); expect(store.error).toBe('')
})


describe('batched Run events', () => {
  const event = (seq: number, type = 'assistant.delta') => ({ runId: 'r1', seq, createdAt: '', type, payload: { text: String(seq) } })
  it('uses the subscription snapshot without fetching it again or loading artifacts twice on connect', async () => {
    const store = useAgentRunStore(); store.openRun('r1')
    options.onSnapshot?.(snapshot()); options.onConnected?.(snapshot())
    await vi.advanceTimersByTimeAsync(0)
    expect(api.fetchAgentRun).not.toHaveBeenCalled()
    expect(api.fetchRunArtifacts).toHaveBeenCalledTimes(1)
  })
  it.each(['waiting_input', 'succeeded'] as const)('commits ordered events once per 100 ms and retains the %s snapshot', async status => {
    const store = useAgentRunStore(); store.openRun('r1')
    options.onSnapshot?.(snapshot({ status: 'running', lastSeq: 0, actions: [] }))
    await vi.advanceTimersByTimeAsync(0)
    vi.mocked(api.fetchAgentRun).mockClear(); vi.mocked(api.fetchRunArtifacts).mockClear()
    vi.mocked(api.fetchAgentRun).mockResolvedValue(snapshot({ status, lastSeq: 4, actions: status === 'waiting_input' ? [action] : [] }))
    options.onEvent(event(1)); options.onEvent(event(2, 'run.status')); options.onEvent(event(2, 'run.status'))
    options.onEvent(event(3, 'artifact.created')); options.onEvent(event(4, status === 'waiting_input' ? 'action.required' : 'run.status'))
    expect(store.events).toEqual([]); expect(api.fetchAgentRun).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(99); expect(store.events).toEqual([])
    await vi.advanceTimersByTimeAsync(1)
    expect(store.events.map(item => item.seq)).toEqual([1, 2, 3, 4])
    expect(api.fetchAgentRun).toHaveBeenCalledTimes(1); expect(api.fetchRunArtifacts).toHaveBeenCalledTimes(1)
    expect(store.snapshot?.status).toBe(status)
    expect(store.snapshot?.actions).toEqual(status === 'waiting_input' ? [action] : [])
  })
  it('flushes a full batch rather than retaining an unbounded replay queue', async () => {
    const store = useAgentRunStore(); store.openRun('r1')
    for (let seq = 1; seq <= 101; seq++) options.onEvent(event(seq))
    expect(store.events).toHaveLength(100)
    await vi.advanceTimersByTimeAsync(100)
    expect(store.events.map(item => item.seq)).toEqual(Array.from({ length: 101 }, (_, index) => index + 1))
  })
  it.each(['navigation', 'logout', 'reset'])('discards an uncommitted batch after %s', async reason => {
    const store = useAgentRunStore(); store.openRun('r1'); const previous = options
    previous.onEvent(event(1, 'run.status'))
    if (reason === 'navigation') store.openRun('r2')
    else if (reason === 'logout') useAuthStore().token = 'another-account'
    else previous.onReset?.(snapshot({ lastSeq: 8 }))
    await vi.advanceTimersByTimeAsync(100)
    expect(store.events).toEqual([]); expect(api.fetchAgentRun).not.toHaveBeenCalled()
  })
  it('coalesces in-flight refreshes and follows up for a later pending action', async () => {
    const store = useAgentRunStore(); store.openRun('r1')
    options.onSnapshot?.(snapshot({ status: 'running', lastSeq: 0, actions: [] })); await vi.advanceTimersByTimeAsync(0)
    let resolveFirst!: (value: RunSnapshot) => void
    vi.mocked(api.fetchAgentRun).mockClear().mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve })).mockResolvedValueOnce(snapshot({ lastSeq: 3 }))
    options.onEvent(event(1, 'run.status')); await vi.advanceTimersByTimeAsync(100)
    options.onEvent(event(2, 'artifact.created')); options.onEvent(event(3, 'action.required')); await vi.advanceTimersByTimeAsync(100)
    expect(api.fetchAgentRun).toHaveBeenCalledTimes(1)
    resolveFirst(snapshot({ status: 'running', lastSeq: 1, actions: [] })); await vi.advanceTimersByTimeAsync(0)
    expect(api.fetchAgentRun).toHaveBeenCalledTimes(2)
    expect(store.snapshot?.actions).toEqual([action]); expect(store.snapshot?.lastSeq).toBe(3)
  })
})

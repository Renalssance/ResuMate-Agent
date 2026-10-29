import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAgentRunStore } from './agentRun'
import { useAuthStore } from './auth'
import * as api from '../api/agentRuns'
import { subscribeRun, type RunSnapshot, type RunSubscriptionOptions } from '../services/agentStream'
vi.mock('../api/agentRuns', () => ({ fetchAgentRuns: vi.fn(), fetchAgentRun: vi.fn(), fetchRunArtifacts: vi.fn(), createAgentRun: vi.fn(), answerRunAction: vi.fn(), cancelAgentRun: vi.fn(), retryAgentRun: vi.fn(), AgentRunError: class extends Error { constructor(public status: number, public code: string, message: string) { super(message) } } }))
vi.mock('../services/agentStream', () => ({ subscribeRun: vi.fn() }))
const action = { actionId: 'a1', kind: 'input' as const, payload: { question: '你负责什么工作？' }, revision: 1 }
const snapshot = (overrides: Partial<RunSnapshot> = {}): RunSnapshot => ({ runId: 'r1', sessionId: 's1', kind: 'tailoring', status: 'waiting_input', input: { jdId: 1, resumeId: 2 }, inputVersions: {}, attempt: 1, lastSeq: 4, errorCode: null, cancelRequested: false, outputRefs: [], actions: [action], ...overrides })
let options: RunSubscriptionOptions
let close: ReturnType<typeof vi.fn<() => void>>
beforeEach(() => { setActivePinia(createPinia()); vi.resetAllMocks(); close = vi.fn(); vi.mocked(subscribeRun).mockImplementation((value) => { options = value; return { close, done: Promise.resolve() } }); vi.mocked(api.fetchRunArtifacts).mockResolvedValue([]); vi.mocked(api.fetchAgentRun).mockResolvedValue(snapshot()) })
describe('persistent task workspace', () => {
  it('keeps the authoritative snapshot while replaying older statuses, and disconnect never fails a run', () => {
    const store = useAgentRunStore(); store.openRun('r1'); options.onSnapshot?.(snapshot())
    options.onEvent({ runId: 'r1', seq: 1, createdAt: '', type: 'run.status', payload: { status: 'running' } }); options.onError?.(new TypeError('offline'))
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

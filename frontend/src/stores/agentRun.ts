import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { useAuthStore } from './auth'
import { subscribeRun, type RunEvent, type RunSnapshot, type RunSubscription } from '../services/agentStream'
import { AgentRunError, answerRunAction, cancelAgentRun, createAgentRun, fetchAgentRun, fetchAgentRuns, fetchRunArtifacts, retryAgentRun, type AgentRunItem, type RunAction, type RunArtifact } from '../api/agentRuns'

export const useAgentRunStore = defineStore('agentRun', () => {
  const runs = ref<AgentRunItem[]>([]), hasMore = ref(false), listLoading = ref(false)
  const snapshot = ref<RunSnapshot | null>(null), events = ref<RunEvent[]>([]), artifacts = ref<RunArtifact[]>([])
  const drafts = ref<Record<string, string>>({}), actionErrors = ref<Record<string, string>>({}), conflictedActions = ref<RunAction[]>([])
  const error = ref(''), notice = ref(''), disconnected = ref(false), loginRequired = ref(false), loading = ref(false), busy = ref(false)
  let subscription: RunSubscription | undefined, generation = 0, selectedId = '', listGeneration = 0
  let pendingEvents: RunEvent[] = [], batchTimer: ReturnType<typeof setTimeout> | undefined, lastEventSeq = 0
  let refreshRequestedSeq = 0, eventRefresh: Promise<void> | undefined
  let createIntent: { key: string; requestId: string } | undefined
  const auth = useAuthStore()
  watch(() => auth.token, () => clear(), { flush: 'sync' })

  function fail(cause: unknown) {
    const status = cause && typeof cause === 'object' && 'status' in cause ? Number(cause.status) : 0
    if (status === 401 || status === 403) { clear(); loginRequired.value = true; error.value = '请重新登录后查看你的任务'; return }
    error.value = cause instanceof Error ? cause.message : '请求失败，请重试'
  }
  function discardBatch() {
    clearTimeout(batchTimer); batchTimer = undefined; pendingEvents = []
  }
  function disconnect() {
    generation++; subscription?.close(); subscription = undefined; discardBatch()
    lastEventSeq = 0; refreshRequestedSeq = 0; eventRefresh = undefined; loading.value = false; busy.value = false
  }
  function clear() {
    disconnect(); listGeneration++; selectedId = ''; runs.value = []; hasMore.value = false; listLoading.value = false
    snapshot.value = null; events.value = []; artifacts.value = []; drafts.value = {}; actionErrors.value = {}; conflictedActions.value = []
    error.value = ''; notice.value = ''; disconnected.value = false; loginRequired.value = false; createIntent = undefined
  }
  async function loadRuns(more = false) {
    const epoch = ++listGeneration; listLoading.value = true
    try { const result = await fetchAgentRuns(more ? runs.value.length : 0); if (epoch !== listGeneration) return
      runs.value = more ? [...runs.value, ...result.items] : result.items; hasMore.value = result.hasMore
    } catch (cause) { if (epoch === listGeneration) fail(cause) }
    finally { if (epoch === listGeneration) listLoading.value = false }
  }
  function applySnapshot(value: RunSnapshot) {
    if (value.runId !== selectedId || (snapshot.value && value.lastSeq < snapshot.value.lastSeq)) return
    // A second tab can answer while this tab has an unsent answer. Keep it visible.
    for (const action of snapshot.value?.actions || []) {
      if (drafts.value[action.actionId]?.trim() && !value.actions.some(item => item.actionId === action.actionId) && !conflictedActions.value.some(item => item.actionId === action.actionId)) {
        conflictedActions.value.push(action); notice.value = '任务状态已变化，其他页面可能已处理该问题。你的未提交回答已保留。'
      }
    }
    snapshot.value = value; loading.value = false
    const item = runs.value.find(item => item.runId === value.runId)
    if (item) item.status = value.status
  }
  async function refresh() {
    const epoch = generation, id = selectedId
    if (!id) return
    try {
      const [value, output] = await Promise.all([fetchAgentRun(id), fetchRunArtifacts(id)])
      if (epoch !== generation || (snapshot.value && value.lastSeq < snapshot.value.lastSeq)) return
      applySnapshot(value); artifacts.value = output
    } catch (cause) { if (epoch === generation) fail(cause) }
  }
  async function refreshArtifacts(value: RunSnapshot) {
    const epoch = generation
    try {
      const output = await fetchRunArtifacts(value.runId)
      if (epoch === generation && snapshot.value?.lastSeq === value.lastSeq) artifacts.value = output
    } catch (cause) { if (epoch === generation) fail(cause) }
  }
  function refreshForEvents(seq: number) {
    refreshRequestedSeq = Math.max(refreshRequestedSeq, seq)
    if (eventRefresh || refreshRequestedSeq <= (snapshot.value?.lastSeq ?? 0)) return
    const epoch = generation
    const update = async () => {
      while (epoch === generation && refreshRequestedSeq > (snapshot.value?.lastSeq ?? 0)) {
        const requested = refreshRequestedSeq
        await refresh()
        // A later batch may arrive during this request. Retry only for that batch,
        // never loop on a failed request or a snapshot that has not caught up yet.
        if (refreshRequestedSeq === requested) break
      }
    }
    const pending = update().finally(() => { if (eventRefresh === pending) eventRefresh = undefined })
    eventRefresh = pending
  }
  function flushBatch() {
    clearTimeout(batchTimer); batchTimer = undefined
    const batch = pendingEvents; pendingEvents = []
    if (!batch.length) return
    events.value.push(...batch)
    // Replay remains history; only the SQL snapshot supplies status and actions.
    const seq = batch.reduce((latest, event) => ['run.status', 'action.required', 'artifact.created'].includes(event.type) ? Math.max(latest, event.seq) : latest, 0)
    if (seq) refreshForEvents(seq)
  }
  function connect(epoch: number) {
    subscription?.close()
    const accept = (value: RunSnapshot) => {
      if (epoch !== generation || value.lastSeq < (snapshot.value?.lastSeq ?? -1)) return
      applySnapshot(value); void refreshArtifacts(value)
    }
    subscription = subscribeRun({
      runId: selectedId, onSnapshot: accept,
      onReset: (value) => {
        if (epoch !== generation) return
        discardBatch(); events.value = []; lastEventSeq = value.lastSeq; accept(value)
      },
      onConnected: (value) => {
        if (epoch !== generation) return
        disconnected.value = false
        if (value.lastSeq > (snapshot.value?.lastSeq ?? -1)) accept(value)
      },
      onEvent: (event) => {
        if (epoch !== generation) return
        disconnected.value = false
        // subscribeRun validates contiguous sequence numbers before delivery.
        if (event.seq <= lastEventSeq) return
        lastEventSeq = event.seq; pendingEvents.push(event)
        if (pendingEvents.length >= 100) flushBatch()
        else batchTimer ??= setTimeout(flushBatch, 100)
      },
      onError: (cause) => {
        if (epoch !== generation) return
        loading.value = false
        const status = 'status' in cause ? Number(cause.status) : 0
        if (status >= 400 && status < 500 && status !== 429) fail(cause)
        else disconnected.value = true
      },
    })
  }
  function openRun(id: string) {
    disconnect(); selectedId = id; snapshot.value = null; events.value = []; artifacts.value = []; drafts.value = {}; actionErrors.value = {}; conflictedActions.value = []
    error.value = ''; notice.value = ''; disconnected.value = false; loginRequired.value = false
    if (!id) return
    loading.value = true; connect(generation)
  }
  async function createRun(jd: string, resume: string) {
    if (busy.value) return
    const epoch = generation, key = `${jd}/${resume}`
    if (createIntent?.key !== key) createIntent = { key, requestId: crypto.randomUUID() }
    busy.value = true; error.value = ''
    try {
      const result = await createAgentRun({ kind: 'tailoring', jdId: Number(jd.split(':').pop()), resumeId: Number(resume.split(':').pop()), requestId: createIntent.requestId })
      if (epoch !== generation) return
      createIntent = undefined; void loadRuns(); return result.runId
    } catch (cause) { if (epoch === generation) fail(cause) }
    finally { if (epoch === generation) busy.value = false }
  }
  async function submitAction(action: RunAction, decision: 'submit' | 'approve' | 'reject' = 'submit') {
    if (busy.value) return
    if (decision === 'submit' && !drafts.value[action.actionId]?.trim()) { actionErrors.value[action.actionId] = '请填写补充信息'; return }
    const epoch = generation, id = selectedId
    busy.value = true; actionErrors.value[action.actionId] = ''; notice.value = ''
    try {
      await answerRunAction(id, action.actionId, { decision, answers: decision === 'submit' ? { answer: drafts.value[action.actionId].trim() } : {}, expectedRevision: action.revision })
      if (epoch !== generation) return
      delete drafts.value[action.actionId]; conflictedActions.value = conflictedActions.value.filter(item => item.actionId !== action.actionId)
      notice.value = '回答已提交'; await refresh(); if (epoch === generation) connect(epoch)
    } catch (cause) {
      if (epoch !== generation) return
      if (cause instanceof AgentRunError && cause.status === 409) {
        notice.value = '任务状态已变化，其他页面可能已处理该问题。你的未提交回答已保留。'
        if (!conflictedActions.value.some(item => item.actionId === action.actionId)) conflictedActions.value.push(action)
        await refresh()
      } else { actionErrors.value[action.actionId] = cause instanceof Error ? cause.message : '提交失败，请重试'; fail(cause) }
    } finally { if (epoch === generation) busy.value = false }
  }
  async function changeRun(operation: 'cancel' | 'retry') {
    if (busy.value || !selectedId) return
    const epoch = generation; busy.value = true; error.value = ''
    try { await (operation === 'cancel' ? cancelAgentRun(selectedId) : retryAgentRun(selectedId)); if (epoch !== generation) return; await refresh(); if (epoch === generation) connect(epoch) }
    catch (cause) {
      if (epoch !== generation) return
      if (cause instanceof AgentRunError && cause.status === 409 && cause.code === 'session_context_invalidated') {
        await refresh()
        if (epoch === generation) notice.value = '这项任务使用的记忆已删除，旧会话不能恢复。请重新准备材料。'
      } else fail(cause)
    }
    finally { if (epoch === generation) busy.value = false }
  }
  return { runs, hasMore, listLoading, snapshot, events, artifacts, drafts, actionErrors, conflictedActions, error, notice, disconnected, loginRequired, loading, busy, loadRuns, openRun, refresh, disconnect, clear, createRun, submitAction, changeRun }
})

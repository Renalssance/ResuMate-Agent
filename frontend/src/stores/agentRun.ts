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
  let createIntent: { key: string; requestId: string } | undefined
  const auth = useAuthStore()
  watch(() => auth.token, () => clear(), { flush: 'sync' })

  function fail(cause: unknown) {
    const status = cause && typeof cause === 'object' && 'status' in cause ? Number(cause.status) : 0
    if (status === 401 || status === 403) { clear(); loginRequired.value = true; error.value = '请重新登录后查看你的任务'; return }
    error.value = cause instanceof Error ? cause.message : '请求失败，请重试'
  }
  function disconnect() { generation++; subscription?.close(); subscription = undefined; loading.value = false; busy.value = false }
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
  function connect(epoch: number) {
    subscription?.close()
    const accept = (value: RunSnapshot) => { if (epoch !== generation) return; applySnapshot(value); void refresh() }
    subscription = subscribeRun({
      runId: selectedId, onSnapshot: accept, onReset: (value) => { if (epoch !== generation) return; events.value = []; accept(value) },
      onConnected: (value) => {
        if (epoch !== generation) return
        disconnected.value = false
        const newer = value.lastSeq > (snapshot.value?.lastSeq ?? -1)
        applySnapshot(value)
        if (newer) void refresh()
      },
      onEvent: (event) => {
        if (epoch !== generation) return
        disconnected.value = false
        if (!events.value.some(item => item.seq === event.seq)) events.value.push(event)
        // Replay is history, never an authoritative status update.
        if (event.seq > (snapshot.value?.lastSeq ?? 0) && ['run.status', 'action.required', 'artifact.created'].includes(event.type)) void refresh()
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
    catch (cause) { if (epoch === generation) fail(cause) }
    finally { if (epoch === generation) busy.value = false }
  }
  return { runs, hasMore, listLoading, snapshot, events, artifacts, drafts, actionErrors, conflictedActions, error, notice, disconnected, loginRequired, loading, busy, loadRuns, openRun, refresh, disconnect, clear, createRun, submitAction, changeRun }
})

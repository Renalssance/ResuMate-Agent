import { computed, onUnmounted, readonly, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { answerRunAction, fetchAgentRun, type RunAction } from '../api/agentRuns'
import { importLocalDocument } from '../api/documentImports'
import type { BackendDocumentParseResult } from '../api/documents'
import { subscribeRun, type RunSnapshot, type RunSubscription } from '../services/agentStream'
import { toDocumentRecord } from '../stores/document'
import type { DocumentRecord, DocumentType } from '../types/document'

export type ImportState = 'idle' | 'uploading' | 'processing' | 'waiting_input' | 'succeeded' | 'failed'

export function useDocumentImport(storageScope: MaybeRefOrGetter<string>) {
  const state = ref<ImportState>('idle')
  const pendingAction = ref<RunAction | null>(null)
  const resultDocument = ref<DocumentRecord | null>(null)
  const error = ref('')
  const savedRunKey = computed(() => `resumate:document-import:${toValue(storageScope)}`)
  let subscription: RunSubscription | undefined
  let runId = '', generation = 0, uploadGeneration = 0, lastSeq = -1

  function closeSubscription() {
    subscription?.close()
    subscription = undefined
  }

  function clearState() {
    generation++
    closeSubscription()
    runId = ''; lastSeq = -1
    state.value = 'idle'; pendingAction.value = null
    resultDocument.value = null; error.value = ''
  }

  function applySnapshot(snapshot: RunSnapshot) {
    if (snapshot.lastSeq < lastSeq) return
    lastSeq = snapshot.lastSeq
    error.value = ''
    state.value = snapshot.status === 'waiting_input' ? 'waiting_input' :
      snapshot.status === 'succeeded' ? 'succeeded' :
      snapshot.status === 'failed' || snapshot.status === 'cancelled' ? 'failed' : 'processing'
    pendingAction.value = state.value === 'waiting_input'
      ? snapshot.actions.find(action => action.kind === 'input' && Array.isArray(action.payload.choices)) || null
      : null
    if (state.value === 'succeeded') {
      const document = (snapshot.result?.documents as BackendDocumentParseResult[] | undefined)?.[0]
      resultDocument.value = document ? toDocumentRecord(document) : null
    }
    if (state.value === 'failed') error.value = snapshot.errorCode || '文件导入失败'
    if (state.value === 'succeeded' || state.value === 'failed') {
      sessionStorage.removeItem(savedRunKey.value)
      closeSubscription()
    }
  }

  async function refresh(version: number) {
    try {
      const snapshot = await fetchAgentRun(runId)
      if (version === generation) applySnapshot(snapshot)
    } catch (value) {
      if (version === generation) error.value = value instanceof Error ? value.message : '文件导入失败'
    }
  }

  function connect(version: number) {
    const receive = (snapshot: RunSnapshot) => { if (version === generation) applySnapshot(snapshot) }
    subscription = subscribeRun({
      runId, onSnapshot: receive, onReset: receive,
      onEvent: event => {
        if (version === generation && (event.type === 'run.status' || event.type === 'action.required')) {
          void refresh(version)
        }
      },
      onError: value => { if (version === generation) error.value = value.message },
    })
  }

  async function resumeImport(savedRunId: string) {
    clearState()
    const version = generation
    runId = savedRunId
    state.value = 'processing'
    sessionStorage.setItem(savedRunKey.value, runId)
    await refresh(version)
    if (version === generation && !['succeeded', 'failed'].includes(state.value)) connect(version)
  }

  async function startImport(file: File) {
    resetImport()
    const version = generation, uploadVersion = uploadGeneration, key = savedRunKey.value
    state.value = 'uploading'
    try {
      const accepted = await importLocalDocument(file, crypto.randomUUID())
      if (uploadVersion !== uploadGeneration) return
      sessionStorage.setItem(key, accepted.runId)
      if (version !== generation) return
      runId = accepted.runId
      state.value = 'processing'
      connect(version)
    } catch (value) {
      if (version !== generation) return
      state.value = 'failed'
      error.value = value instanceof Error ? value.message : '文件导入失败'
    }
  }

  async function confirmDocumentType(type: DocumentType) {
    const action = pendingAction.value, version = generation
    if (!action) return
    try {
      await answerRunAction(runId, action.actionId, {
        decision: 'submit', answers: { documentType: type }, expectedRevision: action.revision,
      })
      if (version !== generation || pendingAction.value?.actionId !== action.actionId) return
      pendingAction.value = null; state.value = 'processing'; error.value = ''
    } catch (value) {
      if (version === generation) error.value = value instanceof Error ? value.message : '文件导入失败'
    }
  }

  function resetImport() {
    uploadGeneration++
    sessionStorage.removeItem(savedRunKey.value)
    clearState()
  }

  watch(savedRunKey, key => {
    const savedRunId = sessionStorage.getItem(key)
    if (savedRunId) void resumeImport(savedRunId)
    else clearState()
  }, { immediate: true, flush: 'sync' })
  onUnmounted(() => { generation++; closeSubscription() })

  return {
    state: readonly(state), pendingAction: readonly(pendingAction),
    resultDocument: readonly(resultDocument), error: readonly(error),
    startImport, resumeImport, confirmDocumentType, resetImport,
  }
}

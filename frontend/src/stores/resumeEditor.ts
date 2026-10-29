import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import type { ReviewDecision, ResumeVersionArtifact } from '../api/agentRuns'
import { confirmResumeVersion, fetchResumeVersion, saveResumeVersion } from '../api/resumeVersions'
import { decisionsFor, projectResume, reviewChanges, sameDecision } from '../utils/resumeReview'
import { useAuthStore } from './auth'

export const useResumeEditorStore = defineStore('resumeEditor', () => {
  const serverSnapshot = ref<ResumeVersionArtifact | null>(null)
  const localDecisions = ref<Record<string, ReviewDecision>>({})
  const conflictLatest = ref<ResumeVersionArtifact | null>(null), conflict = ref(false)
  const loading = ref(false), busy = ref(false), error = ref(''), notice = ref('')
  let generation = 0, selectedId = ''
  const auth = useAuthStore()
  watch(() => auth.token, clear, { flush: 'sync' })
  const changes = computed(() => reviewChanges(serverSnapshot.value) || [])
  const reviewable = computed(() => reviewChanges(serverSnapshot.value) !== null)
  const baseline = computed(() => decisionsFor(changes.value))
  const dirty = computed(() => changes.value.some(change => !sameDecision(localDecisions.value[change.id], baseline.value[change.id])))
  const editable = computed(() => !!serverSnapshot.value && serverSnapshot.value.status === 'draft' && reviewable.value && !busy.value && !loading.value && !conflict.value)
  const reviewedCount = computed(() => changes.value.filter(change => localDecisions.value[change.id]?.status !== 'pending').length)
  const preview = computed(() => projectResume(serverSnapshot.value, localDecisions.value))
  const canSave = computed(() => editable.value && dirty.value)
  const canConfirm = computed(() => editable.value && !dirty.value && reviewedCount.value === changes.value.length)

  function clear() {
    generation++; selectedId = ''; serverSnapshot.value = null; localDecisions.value = {}; conflictLatest.value = null
    loading.value = false; busy.value = false; conflict.value = false; error.value = ''; notice.value = ''
  }
  function adopt(value: ResumeVersionArtifact) {
    serverSnapshot.value = value; localDecisions.value = decisionsFor(reviewChanges(value) || [])
    conflict.value = false; conflictLatest.value = null
  }
  async function loadVersion(id: string) {
    clear(); selectedId = id; const epoch = generation; loading.value = true
    try { const value = await fetchResumeVersion(id); if (epoch === generation) adopt(value) }
    catch (cause) { if (epoch === generation) error.value = cause instanceof Error ? cause.message : '无法加载这个版本，请重试' }
    finally { if (epoch === generation) loading.value = false }
  }
  function decide(decision: ReviewDecision) {
    if (!editable.value) return
    const change = changes.value.find(item => item.id === decision.id)
    if (!change || (decision.status === 'accepted' && change.requires_input)) return
    localDecisions.value[decision.id] = decision.status === 'edited'
      ? { id: decision.id, status: decision.status, editedText: decision.editedText ?? '' }
      : { id: decision.id, status: decision.status }
    notice.value = ''; error.value = ''
  }
  async function loadConflict() {
    if (!conflict.value || !selectedId) return
    const epoch = generation
    try { const latest = await fetchResumeVersion(selectedId); if (epoch === generation) { conflictLatest.value = latest; error.value = '' } }
    catch { if (epoch === generation) error.value = '暂时无法加载服务器最新版本。你的修改仍保留，请重试。' }
  }
  async function persist(operation: 'save' | 'confirm') {
    if ((operation === 'save' ? !canSave.value : !canConfirm.value) || !serverSnapshot.value) return
    const epoch = generation, id = selectedId, revision = serverSnapshot.value.revision
    const submitted = changes.value.map(change => ({ ...localDecisions.value[change.id]! }))
    busy.value = true; error.value = ''; notice.value = ''
    try {
      const result = operation === 'save' ? await saveResumeVersion(id, revision, submitted) : await confirmResumeVersion(id, revision)
      if (epoch !== generation) return
      adopt(result); notice.value = operation === 'save' ? `草稿已保存 · 第 ${result.revision} 版` : '版本已确认，内容已冻结'
    } catch (cause) {
      if (epoch !== generation) return
      if (cause && typeof cause === 'object' && 'status' in cause && cause.status === 409) {
        conflict.value = true; await loadConflict()
      } else error.value = cause instanceof Error ? cause.message : '保存失败，请重试。你的修改仍保留。'
    } finally { if (epoch === generation) busy.value = false }
  }
  function useServerVersion() {
    if (!conflictLatest.value || busy.value) return
    adopt(conflictLatest.value); error.value = ''; notice.value = '已使用服务器最新版本'
  }
  function applyLocalChanges() {
    if (!conflictLatest.value || conflictLatest.value.status !== 'draft' || !reviewChanges(conflictLatest.value) || busy.value) return
    const changed = Object.values(localDecisions.value).filter(decision => !sameDecision(decision, baseline.value[decision.id]))
    adopt(conflictLatest.value)
    for (const decision of changed) if (localDecisions.value[decision.id]) localDecisions.value[decision.id] = decision
    error.value = ''; notice.value = '已将本页修改应用到最新版本，请核对后再次保存'
  }
  return { serverSnapshot, localDecisions, conflictLatest, conflict, loading, busy, error, notice, changes, reviewable, dirty, editable, reviewedCount, preview, canSave, canConfirm,
    clear, loadVersion, decide, loadConflict, save: () => persist('save'), confirm: () => persist('confirm'), useServerVersion, applyLocalChanges }
})

<template>
  <div class="page-stack">
    <section class="card workflow-card">
      <div class="section-head"><div><h2>准备投递材料</h2><p>选择目标岗位和主简历，准备一份可核对的投递材料。离开页面后任务会继续。</p></div></div>
      <p v-if="!auth.isAuthenticated || store.loginRequired" class="login-note">请<RouterLink to="/login">登录</RouterLink>后准备和查看你的材料。</p>
      <form v-else class="prepare-form" @submit.prevent="createTask">
        <label class="workflow-row"><span>目标岗位</span><select v-model="jdId" required><option value="">请选择岗位</option><option v-for="doc in documents.parsedJds" :key="doc.id" :value="doc.id">{{ doc.parsedContent?.title || doc.filename }}</option></select></label>
        <label class="workflow-row"><span>主简历</span><select v-model="resumeId" required><option value="">请选择简历</option><option v-for="doc in documents.parsedResumes" :key="doc.id" :value="doc.id">{{ formatResumeLabel(doc) }}</option></select></label>
        <button class="button-primary" type="submit" :disabled="!jdId || !resumeId || store.busy">{{ store.busy && !store.snapshot ? '正在提交…' : '开始准备' }}</button>
      </form>
      <p v-if="auth.isAuthenticated && !documents.listLoading && (!documents.parsedJds.length || !documents.parsedResumes.length)" class="muted-note">请先在<RouterLink to="/documents">文档管理</RouterLink>上传并解析岗位和简历。</p>
      <p v-if="documents.error" class="error-note" role="alert">{{ documents.error }}</p>
      <p v-if="store.error" class="error-note" role="alert">{{ store.error }}</p>
    </section>

    <div v-if="auth.isAuthenticated && !store.loginRequired" class="task-workspace">
      <section class="card workflow-card task-list">
        <div class="section-head"><h2>我的任务</h2><button class="button-secondary" type="button" :disabled="store.listLoading" @click="store.loadRuns()">刷新任务</button></div>
        <p v-if="store.listLoading && !store.runs.length">正在加载任务…</p>
        <p v-else-if="!store.runs.length" class="muted-note">选择岗位和简历，开始准备第一份材料。</p>
        <ul v-else class="task-links"><li v-for="run in store.runs" :key="run.runId"><RouterLink :to="`/agent/tasks/${run.runId}`" :aria-current="selectedRunId === run.runId ? 'page' : undefined"><strong>{{ taskTitle(run.input, run.kind) }}</strong><span>{{ taskStatusLabel(run.status, run.kind) }}</span><time>{{ formatDate(run.createdAt) }}</time></RouterLink></li></ul>
        <button v-if="store.hasMore" class="button-secondary" type="button" :disabled="store.listLoading" @click="store.loadRuns(true)">加载更多任务</button>
      </section>
      <section v-if="selectedRunId" class="card workflow-card task-detail" aria-label="任务详情" :aria-busy="store.loading">
        <p v-if="store.loading">正在读取任务…</p>
        <p v-if="store.disconnected" class="connection-note" role="status">网络连接已断开，正在重新连接。任务会继续运行。</p>
        <template v-if="store.snapshot">
          <div class="section-head"><div><h2 ref="statusHeading" tabindex="-1">{{ taskStatusLabel(store.snapshot.status, store.snapshot.kind) }}</h2><p>{{ taskTitle(store.snapshot.input, store.snapshot.kind) }}</p></div><div class="run-buttons"><button v-if="store.snapshot.status === 'failed' && !sessionInvalidated" class="button-primary" type="button" :disabled="store.busy" @click="store.changeRun('retry')">重试任务</button><button v-else-if="!terminal" class="button-secondary" type="button" :disabled="store.busy || store.snapshot.cancelRequested" @click="store.changeRun('cancel')">{{ store.snapshot.cancelRequested ? '正在取消…' : '取消任务' }}</button></div></div>
          <div v-if="store.snapshot.status === 'failed' || (store.snapshot.status === 'cancelled' && sessionInvalidated)" class="task-failure" role="alert">
            <p class="error-note">{{ failureMessage }}</p>
            <RouterLink v-if="contextSettingsRequired" class="task-settings-link" to="/settings">前往模型设置</RouterLink>
            <button v-if="sessionInvalidated" class="button-primary" type="button" :disabled="store.busy" @click="prepareFreshTask">重新准备材料</button>
          </div>
          <p v-if="store.notice" class="notice" role="status">{{ store.notice }}</p>
          <RunTimeline :events="store.events" :status="store.snapshot.status" :kind="store.snapshot.kind" />
          <ActionForm v-for="action in visibleActions" :key="action.actionId" :model-value="store.drafts[action.actionId] || ''" @update:model-value="value => updateAnswer(action.actionId, value)" :action="action" :busy="store.busy" :error="store.actionErrors[action.actionId] || ''" :inactive="!acceptsAnswers || !store.snapshot.actions.some(item => item.actionId === action.actionId)" @submit="decision => store.submitAction(action, decision)" />
          <template v-for="artifact in store.artifacts" :key="artifact.id"><PdfArtifactCard v-if="artifact.kind === 'resume_pdf'" :artifact="artifact" /><ArtifactCard v-else :artifact="artifact" /></template>
          <LongTaskResult v-if="longTask && store.snapshot.result" :kind="store.snapshot.kind" :result="store.snapshot.result" />
          <p v-if="store.snapshot.status === 'succeeded' && !store.artifacts.length && !longTask" class="muted-note">{{ store.snapshot.kind === 'resume_export' ? 'PDF 已完成，正在读取下载信息。' : '材料已完成，正在读取草稿。' }}<button class="button-secondary" type="button" @click="store.refresh()">重新读取材料</button></p>
        </template>
        <button v-else-if="!store.loading && !store.loginRequired" class="button-secondary" type="button" @click="store.openRun(selectedRunId)">重新连接任务</button>
      </section>
      <section v-else class="card workflow-card muted-note">选择一个任务，查看进度、补充经历和生成的材料。</section>
    </div>
    <p class="sr-only" aria-live="polite" aria-atomic="true">{{ announcement }}</p>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useDocumentStore } from '../stores/document'
import { useAgentRunStore } from '../stores/agentRun'
import { taskStatusLabel } from '../api/agentRuns'
import { formatResumeLabel } from '../utils/format'
import RunTimeline from '../components/agent/RunTimeline.vue'
import LongTaskResult from '../components/agent/LongTaskResult.vue'
import ActionForm from '../components/agent/ActionForm.vue'
import PdfArtifactCard from '../components/agent/PdfArtifactCard.vue'
import ArtifactCard from '../components/agent/ArtifactCard.vue'
const route = useRoute(), router = useRouter(), auth = useAuthStore(), documents = useDocumentStore(), store = useAgentRunStore()
const jdId = ref(''), resumeId = ref(''), statusHeading = ref<HTMLElement | null>(null), announcement = ref('')
const selectedRunId = computed(() => String(route.params.runId || ''))
const longTaskTitles: Record<string, string> = { document_parse: '文档解析', match_analysis: '岗位匹配', question_generation: '面试出题', answer_followup: '回答分析' }
const longTask = computed(() => Boolean(longTaskTitles[store.snapshot?.kind || '']))
const terminal = computed(() => ['succeeded', 'failed', 'cancelled'].includes(store.snapshot?.status || ''))
const acceptsAnswers = computed(() => ['waiting_input', 'waiting_approval'].includes(store.snapshot?.status || ''))
const visibleActions = computed(() => [...(store.snapshot?.actions || []).filter(action => acceptsAnswers.value || store.drafts[action.actionId]?.trim()), ...store.conflictedActions.filter(action => !store.snapshot?.actions.some(item => item.actionId === action.actionId))])
const sessionInvalidated = computed(() => store.snapshot?.kind !== 'resume_export' && (store.snapshot?.sessionInvalidated || store.snapshot?.errorCode === 'session_context_invalidated'))
const contextSettingsRequired = computed(() => !sessionInvalidated.value && store.snapshot?.kind !== 'resume_export' && ['model_context_not_configured', 'context_budget_exceeded'].includes(store.snapshot?.errorCode || ''))
const failureMessage = computed(() => {
  if (longTask.value) return `${longTaskTitles[store.snapshot!.kind]}未完成。你可以重试任务，或返回原页面核对输入资料。`
  if (store.snapshot?.kind === 'resume_export') return 'PDF 导出未完成。你可以重试任务，继续使用已确认的简历内容。'
  if (sessionInvalidated.value) return '这项任务使用的记忆已删除，旧会话不能恢复。请重新准备材料，新任务不会沿用已删除的记忆。已生成的简历和投递版本仍保留。'
  if (store.snapshot?.errorCode === 'model_context_not_configured') return '尚未配置模型的上下文容量。请按厂商提供的实际容量完成模型设置，再重试任务。'
  if (store.snapshot?.errorCode === 'context_budget_exceeded') return '本次资料超出模型可用上下文容量。请核对厂商提供的容量并在设置中填写正确值，或减少本次资料后重新准备。'
  if (store.snapshot?.errorCode === 'input_changed') return '岗位或简历已变化，请使用当前资料创建新任务。'
  return '材料准备未完成。你可以重试任务，或检查设置后重新准备。'
})
function taskTitle(input: Record<string, unknown>, kind?: string) { if (longTaskTitles[kind || '']) return longTaskTitles[kind || '']!; if (kind === 'resume_export') return '已确认简历 · PDF 导出'; const doc = documents.parsedJds.find(doc => Number(doc.id.split(':').pop()) === Number(input.jdId)); return String(doc?.parsedContent?.title || doc?.filename || '投递材料') }
function formatDate(value: string) { return new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
function updateAnswer(actionId: string, value: string) { store.drafts[actionId] = value; if (value.trim()) store.actionErrors[actionId] = '' }
async function prepareFreshTask() {
  const input = store.snapshot?.input
  if (!input?.jdId || !input?.resumeId) return
  const runId = await store.createRun(`jd:${input.jdId}`, `resume:${input.resumeId}`)
  if (runId) await router.push(`/agent/tasks/${runId}`)
}
async function createTask() { if (!jdId.value || !resumeId.value) return; const runId = await store.createRun(jdId.value, resumeId.value); if (runId) await router.push(`/agent/tasks/${runId}`) }
watch(() => auth.token, (token) => { jdId.value = ''; resumeId.value = ''; if (token) { void documents.loadDocuments(); void store.loadRuns() } }, { immediate: true })
watch([() => route.query.jdId, () => route.query.resumeId, () => documents.parsedJds, () => documents.parsedResumes], () => {
  const jd = String(route.query.jdId || ''), resume = String(route.query.resumeId || '')
  if (jd) jdId.value = documents.parsedJds.find(doc => doc.id === jd || doc.id === `jd:${jd}`)?.id || ''
  if (resume) resumeId.value = documents.parsedResumes.find(doc => doc.id === resume || doc.id === `resume:${resume}`)?.id || ''
}, { immediate: true })
watch([selectedRunId, () => auth.token], ([id, token]) => { store.openRun(token ? id : '') }, { immediate: true })
let announcementTimer: ReturnType<typeof setTimeout> | undefined
watch(() => store.snapshot?.status, (status) => { clearTimeout(announcementTimer); if (status) announcementTimer = setTimeout(() => { announcement.value = taskStatusLabel(status, store.snapshot?.kind) }, 600) })
watch(() => store.busy, async (value, previous) => { if (previous && !value && (!acceptsAnswers.value || !store.snapshot?.actions.length)) { await nextTick(); statusHeading.value?.focus() } })
onBeforeUnmount(() => { clearTimeout(announcementTimer); store.disconnect() })
</script>
<style scoped>
.prepare-form { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; align-items: end; gap: 20px; }
.prepare-form .workflow-row { display: grid; gap: 8px; min-width: 0; } .prepare-form select { min-width: 0; } .muted-note,.login-note { color: var(--color-text-secondary); line-height: 1.7; }
.task-workspace { display: grid; grid-template-columns: minmax(240px, .72fr) minmax(0, 1.7fr); gap: 24px; align-items: start; } .task-detail { display: grid; gap: 24px; overflow-wrap: anywhere; } .task-detail .section-head { margin-bottom: 0; }
.task-list { max-height: 720px; overflow: auto; }
.task-list .section-head { flex-wrap: wrap; gap: 12px; } .task-links { padding: 0; margin: 0; list-style: none; display: grid; gap: 10px; } .task-links a { overflow-wrap: anywhere; min-width: 0; display: grid; gap: 8px; padding: 16px; color: var(--color-text); border: 1px solid var(--color-border); border-radius: var(--radius-sm); text-decoration: none; }
.task-links a[aria-current="page"] { border-color: var(--color-primary-border); background: var(--color-primary-light); } .task-links span,.task-links time { color: var(--color-text-secondary); font-size: 13px; } .run-buttons { display: flex; gap: 8px; }
.connection-note,.notice { padding: 14px 16px; border-radius: var(--radius-sm); color: var(--color-warning); background: var(--surface-panel-muted); line-height: 1.6; }
.task-failure { display: grid; justify-items: start; gap: 12px; line-height: 1.7; } .task-failure p { margin: 0; }
.task-settings-link { display: inline-flex; align-items: center; min-height: 44px; color: var(--color-primary); font-weight: 600; text-underline-offset: 4px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 900px) { .task-workspace,.prepare-form { grid-template-columns: 1fr; } .task-list { max-height: 420px; overflow: auto; } }
</style>

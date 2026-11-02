<template>
  <article class="chat-task" :aria-label="title">
    <div class="task-heading"><strong>{{ title }}</strong><span :class="snapshot?.status"><ExecutionSpinner v-if="!snapshot || ['queued', 'running'].includes(snapshot.status)" />{{ statusLabel }}</span></div>
    <p v-if="error" role="alert">{{ error }} <button type="button" @click="connect">重新连接</button></p>
    <template v-if="snapshot?.status === 'succeeded'">
      <template v-if="snapshot.kind === 'match_analysis' && matchResult">
        <p>{{ matchResult.job_title }}</p>
        <div v-for="candidate in matchResult.candidates" :key="candidate.candidate_id" class="match-result"><span>{{ candidate.candidate_name }}</span><strong>{{ Math.round(candidate.total_score) }} 分</strong><RouterLink :to="`/matching?matchId=${matchResult.run_id}:${candidate.candidate_id}`">查看匹配报告</RouterLink></div>
      </template>
      <div v-else-if="snapshot.kind === 'interview_generation'" class="interview-result"><p v-if="interviewResult?.feedback">{{ interviewResult.feedback.summary }}</p><p v-if="interviewResult?.question"><strong>面试问题：</strong>{{ interviewResult.question.text }}</p><p v-else>本次面试已结束，可回顾你的回答与反馈。</p></div>
      <p v-else-if="snapshot.kind === 'document_parse'">文档解析已保存，可继续分析。</p>
      <p v-else-if="snapshot.kind === 'question_generation'">{{ questionCount }} 道面试题已生成。</p>
      <p v-else-if="snapshot.kind === 'resume_export'">PDF 已导出，可在任务详情下载。</p>
    </template>
    <div class="task-actions">
      <RouterLink :to="detailLink">{{ detailLabel }}</RouterLink>
      <button v-if="snapshot?.status === 'succeeded'" data-continue type="button" @click="$emit('continue', `请查看任务 ${id} 的结果，帮我继续分析下一步。`)">继续分析 <span aria-hidden="true">↗</span></button>
    </div>
  </article>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import ExecutionSpinner from '../ExecutionSpinner.vue'
import { fetchAgentRun, taskStatusLabel } from '../../api/agentRuns'
import { subscribeRun, type RunSnapshot, type RunSubscription } from '../../services/agentStream'
import type { RunSummary } from '../../types/run'
const props = defineProps<{ reference: string }>()
defineEmits<{ continue: [message: string] }>()
const snapshot = ref<RunSnapshot | null>(null), error = ref('')
const id = computed(() => props.reference.slice(props.reference.indexOf(':') + 1))
const titles: Record<string, string> = { document_parse: '文档解析', match_analysis: '岗位匹配', tailoring: '简历材料准备', question_generation: '面试试题', resume_export: '简历 PDF', interview_generation: '模拟面试' }
const title = computed(() => titles[snapshot.value?.kind || ''] || '求职任务')
const matchResult = computed(() => snapshot.value?.kind === 'match_analysis' ? snapshot.value.result as unknown as RunSummary | null : null)
const questionCount = computed(() => Array.isArray(snapshot.value?.result?.formal_questions) ? snapshot.value.result.formal_questions.length : 0)
const interviewResult = computed(() => snapshot.value?.result as { question?: { text: string } | null; feedback?: { summary: string } | null } | null)
const statusLabel = computed(() => {
  if (!snapshot.value) return '正在读取任务…'
  if (snapshot.value.kind !== 'interview_generation') return taskStatusLabel(snapshot.value.status, snapshot.value.kind)
  return ({ queued: '等待生成面试题', running: '正在准备面试题', succeeded: '本轮面试已准备好', failed: '面试题生成失败', cancelled: '已停止生成', waiting_input: '等待补充信息', waiting_approval: '等待审阅' })[snapshot.value.status]
})
const matchingLink = computed(() => {
  const input = snapshot.value?.input || {}
  const params = new URLSearchParams({ taskId: id.value })
  if (input.jdId) params.set('jdId', String(input.jdId))
  const resumeIds = Array.isArray(input.resumeIds) ? input.resumeIds : []
  if (resumeIds[0]) params.set('resumeId', String(resumeIds[0]))
  if (input.analysisJobId) params.set('analysisJobId', String(input.analysisJobId))
  return `/matching?${params.toString()}`
})
const detailLink = computed(() => snapshot.value?.kind === 'interview_generation'
  ? `/interviews/${encodeURIComponent(String(snapshot.value.input.interviewId))}`
  : snapshot.value?.kind === 'match_analysis' ? matchingLink.value : `/agent/tasks/${encodeURIComponent(id.value)}`)
const detailLabel = computed(() => snapshot.value?.kind === 'interview_generation' ? '进入模拟面试'
  : snapshot.value?.kind === 'match_analysis' ? (snapshot.value.status === 'succeeded' ? '查看岗位匹配' : '查看匹配进度')
    : snapshot.value?.status === 'waiting_input' ? '补充信息并继续' : snapshot.value?.status === 'waiting_approval' ? '审阅材料' : '查看任务详情')
let subscription: RunSubscription | undefined, generation = 0
async function refresh(epoch: number) {
  try { const value = await fetchAgentRun(id.value); if (generation === epoch) { snapshot.value = value; error.value = '' } }
  catch (cause) { if (generation === epoch) error.value = cause instanceof Error ? cause.message : '任务读取失败' }
}
function connect() {
  subscription?.close(); const epoch = ++generation; error.value = ''
  const accept = (value: RunSnapshot) => { if (generation === epoch) { snapshot.value = value; error.value = '' } }
  subscription = subscribeRun({ runId: id.value, onSnapshot: accept, onReset: accept, onConnected: accept,
    onEvent: event => { if (generation === epoch && ['run.status', 'artifact.created', 'action.required'].includes(event.type)) void refresh(epoch) },
    onError: cause => { if (generation === epoch) error.value = cause.message },
  })
}
watch(id, connect, { immediate: true })
onBeforeUnmount(() => { generation++; subscription?.close() })
</script>
<style scoped>
.chat-task { border: 1px solid #ded0c2; border-radius: 16px; padding: 17px 19px; background: #fcf8f0; color: #594334; display: grid; gap: 12px; font-size: 13px; }
.task-heading,.task-actions,.match-result { display: flex; align-items: center; flex-wrap: wrap; gap: 10px 16px; }.task-heading { justify-content: space-between; }.task-heading>span { display: inline-flex; align-items: center; gap: 6px; color: #8c7059; font-size: 12px; }.task-heading .succeeded { color: #4b7557; }.task-heading .failed { color: #a74736; }p { margin: 0; line-height: 1.6; }a,button { color: #77543a; min-height: 34px; display: inline-flex; align-items: center; font-weight: 600; }button { cursor: pointer; background: transparent; border: 0; padding: 0; gap: 8px; }.task-actions { border-top: 1px solid #e8ddd0; padding-top: 8px; }.match-result a { margin-left: auto; }a { text-underline-offset: 4px; }
</style>

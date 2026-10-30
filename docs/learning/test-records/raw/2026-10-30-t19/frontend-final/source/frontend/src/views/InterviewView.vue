<template>
  <div class="page-stack interview-page">
    <section class="card interview-heading">
      <div class="section-head">
        <div><p class="interview-eyebrow">基于本次投递 · 文字练习</p><h2>模拟面试</h2><p>一次练习最多八题。这里的回答与反馈只用于练习，不会改写简历或投递进展。</p></div>
        <RouterLink class="button-secondary" to="/applications">返回投递记录</RouterLink>
      </div>
      <div v-if="snapshot" class="interview-source">
        <strong>{{ snapshot.sourceSnapshot.job.company }} · {{ snapshot.sourceSnapshot.job.title }}</strong>
        <span>投递简历 · 第 {{ snapshot.sourceSnapshot.revision }} 版</span>
        <span>岗位取材于练习开始时 · {{ dateLabel(snapshot.sourceSnapshot.job.capturedAt) }}</span>
      </div>
    </section>
    <p v-if="!auth.isAuthenticated" class="card">请先登录，再从投递记录开始练习。</p>
    <p v-else-if="loading && !snapshot" class="card" role="status">正在恢复练习进度…</p>
    <p v-if="error || readError" class="error-note interview-notice" role="alert">{{ error || readError }}</p>
    <section v-if="!snapshot && !loading && auth.isAuthenticated" class="card"><h3>暂时无法读取这次练习</h3><p>从投递记录选择已确认材料开始，或重新读取当前进度。</p><button class="button-secondary" type="button" @click="refresh()">重新读取</button></section>
    <template v-if="snapshot">
      <section class="card interview-progress">
        <div><strong>{{ statusLabel }}</strong><p>{{ snapshot.currentTurn ? `当前第 ${snapshot.currentTurn} / 8 题` : '正在准备第一题' }}</p></div>
        <div class="interview-actions">
          <button class="button-secondary" type="button" :disabled="loading" @click="refresh()">刷新进度</button>
          <button v-if="generating && !snapshot.generation?.cancelRequested && !snapshot.sessionInvalidated" class="button-secondary" type="button" :disabled="sending || !!pending" @click="issue('generation.cancel')">停止生成</button>
          <button v-if="canRetry" class="button-primary" type="button" :disabled="sending || !!pending" @click="issue('generation.retry')">重试生成</button>
          <button v-if="snapshot.status === 'active' && !snapshot.sessionInvalidated" class="button-secondary" type="button" :disabled="sending || !!pending" @click="finishing = !finishing">结束练习</button>
        </div>
        <div v-if="finishing" class="interview-confirm"><p>结束后保留已有问答，并停止正在生成的内容。</p><button class="button-secondary" type="button" @click="finishing = false">继续练习</button><button class="button-primary" type="button" :disabled="sending || !!pending" @click="issue('session.finish')">确认结束练习</button></div>
      </section>
      <p v-if="snapshot.sessionInvalidated" class="interview-notice" role="status">这次练习使用的记忆已删除。请返回投递记录，开始新的练习。</p>
      <p v-else-if="snapshot.generation?.status === 'failed'" class="interview-notice" role="status">本次生成未完成，已接受的回答仍然保留。可以重试生成。</p>
      <section v-if="pending && !sending" class="card interview-pending" aria-label="待确认的操作">
        <h3>尚未确认是否收到{{ pending.type === 'answer.submit' ? '回答' : '操作' }}</h3>
        <p>重新发送会沿用同一次提交。{{ pending.type === 'answer.submit' ? '后续编辑的草稿不会替换原回答。' : '' }}</p>
        <blockquote v-if="pending.type === 'answer.submit'">{{ pending.payload.text }}</blockquote>
        <button class="button-primary" type="button" @click="deliverPending">{{ pending.type === 'answer.submit' ? '重新发送原回答' : '重新发送原操作' }}</button>
      </section>
      <div class="interview-columns">
        <section class="card interview-current" aria-label="当前问题">
          <p class="interview-eyebrow">{{ current ? `第 ${current.turnIndex} 题` : '准备开始' }}<span v-if="current?.questionContext?.mode === 'follow_up'"> · 继续追问</span></p>
          <h3>{{ snapshot.status === 'finished' ? '本次练习已结束' : current ? '说说你的思路' : '正在准备第一题' }}</h3>
          <p v-if="current" class="interview-question">{{ current.question }}</p>
          <p v-else>问题会根据本次投递材料生成。离开页面不会结束练习。</p>
          <InterviewReferences v-if="current?.questionContext?.refs.length" :refs="current.questionContext.refs" />
          <form v-if="canAnswer" @submit.prevent="submitAnswer">
            <label class="form-field"><span>你的回答</span><textarea v-model="draft" rows="8" maxlength="4000" placeholder="说明你做了什么、为什么这样做，以及结果。" /></label>
            <div class="interview-answer-foot"><small>{{ draft.length }} / 4000 字 · 草稿保留在当前浏览器会话</small><button class="button-primary" type="submit" :disabled="!draft.trim() || sending || !!pending">{{ sending ? '正在提交…' : '提交回答' }}</button></div>
          </form>
          <p v-else-if="current?.answer && snapshot.status === 'active'" class="interview-notice">回答已接受。{{ snapshot.sessionInvalidated ? '本次练习已停止继续生成，可以回顾已有回答。' : generating ? '正在整理反馈与下一题。' : '可查看练习反馈，或按当前状态重试生成。' }}</p>
          <p v-if="snapshot.status === 'finished'" class="interview-muted">问答与反馈已保留。你可以回顾练习，再从投递记录开始新一轮。</p>
        </section>
        <section class="card interview-history" aria-label="问答回顾">
          <div class="section-head"><div><h3>问答回顾</h3><p>保留已接受的回答和练习反馈。</p></div></div>
          <p v-if="!answeredTurns.length" class="interview-muted">提交第一份回答后，在这里回顾。</p>
          <article v-for="turn in answeredTurns" :key="turn.id" class="interview-turn">
            <p class="interview-eyebrow">第 {{ turn.turnIndex }} 题</p><h4>{{ turn.question }}</h4>
            <div class="interview-answer"><strong>你的回答</strong><p>{{ turn.answer }}</p></div>
            <div v-if="turn.feedback" class="interview-feedback">
              <h4>练习反馈</h4><p>{{ turn.feedback.summary }}</p>
              <template v-for="group in feedbackGroups(turn.feedback)" :key="group.title">
                <h5 v-if="group.items.length">{{ group.title }}</h5><ul v-if="group.items.length"><li v-for="(item, index) in group.items" :key="index"><p>{{ item.text }}</p><InterviewReferences v-if="item.refs.length" :refs="item.refs" /></li></ul>
              </template>
              <div class="interview-focus"><strong>下次练习要点</strong><p>{{ turn.feedback.practiceFocus }}</p></div>
              <p v-if="turn.feedback.memoryId" class="interview-muted" role="status">已保存练习记忆</p>
              <button v-else class="button-secondary" type="button" :disabled="snapshot.sessionInvalidated" @click="memoryTurn = turn.turnIndex">保存练习要点</button>
              <section v-if="memoryTurn === turn.turnIndex" class="interview-confirm" aria-label="确认练习记忆"><p>确认后，后续练习可以使用这条要点；它不会成为简历事实。</p><blockquote>{{ turn.feedback.practiceFocus }}</blockquote><div class="interview-actions"><button class="button-secondary" type="button" :disabled="savingMemory" @click="memoryTurn = null">暂不保存</button><button class="button-primary" type="button" :disabled="savingMemory" @click="saveMemory(turn)">{{ savingMemory ? '正在保存…' : '确认保存记忆' }}</button></div></section>
            </div>
          </article>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onBeforeUnmount, ref, toRaw, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { fetchInterview, sendInterviewCommand, confirmInterviewMemory } from '../api/interviews'
import { AgentRunError } from '../api/agentRuns'
import { useAuthStore } from '../stores/auth'
import type { InterviewCommand, InterviewFeedback, InterviewRef, InterviewSnapshot, InterviewTurn } from '../types/interview'
const InterviewReferences = defineComponent({ props: { refs: { type: Array as () => InterviewRef[], required: true } }, setup: props => () => h('details', { class: 'interview-references' }, [h('summary', '查看依据'), ...props.refs.map((reference, index) => h('blockquote', { key: index }, [h('small', reference.kind === 'resume' ? `投递简历${reference.section ? ` · ${reference.section}` : ''}` : reference.kind === 'job' ? '岗位要求' : `练习回答 · 第 ${reference.turnIndex} 题`), h('p', reference.quote)]))]) })
const auth = useAuthStore(), route = useRoute()
const interviewId = computed(() => String(route.params.id || ''))
const snapshot = ref<InterviewSnapshot | null>(null), draft = ref(''), pending = ref<InterviewCommand | null>(null)
const loading = ref(false), sending = ref(false), error = ref(''), readError = ref(''), finishing = ref(false), savingMemory = ref(false), memoryTurn = ref<number | null>(null)
let epoch = 0, readRequest = 0, timer: ReturnType<typeof setTimeout> | undefined, activeStorage = '', restoring = false
const current = computed(() => snapshot.value?.turns.find(turn => turn.turnIndex === snapshot.value?.currentTurn))
const answeredTurns = computed(() => snapshot.value?.turns.filter(turn => turn.answer !== null).slice().reverse() || [])
const generating = computed(() => ['queued', 'running'].includes(snapshot.value?.generation?.status || ''))
const canAnswer = computed(() => snapshot.value?.status === 'active' && !snapshot.value.sessionInvalidated && current.value?.answer === null && !generating.value)
const canRetry = computed(() => snapshot.value?.status === 'active' && !snapshot.value.sessionInvalidated && ['failed', 'cancelled'].includes(snapshot.value.generation?.status || ''))
const statusLabel = computed(() => snapshot.value?.sessionInvalidated ? '请开始新的练习' : snapshot.value?.status === 'finished' ? '练习已结束' : generating.value ? snapshot.value?.generation?.cancelRequested ? '正在停止' : '正在生成' : snapshot.value?.generation?.status === 'cancelled' ? '生成已停止' : snapshot.value?.generation?.status === 'failed' ? '生成未完成' : '等待你的回答')
const dateLabel = (value: string) => new Date(value).toLocaleString('zh-CN', { hour12: false })
const feedbackGroups = (feedback: InterviewFeedback) => [{ title: '表达得好的部分', items: feedback.strengths }, { title: '可以补充的部分', items: feedback.improvements }]
const message = (cause: unknown) => cause instanceof Error ? cause.message : '连接未完成，请重试'
const storageRead = (key: string) => { try { return sessionStorage.getItem(key) } catch { return null } }
function storageWrite(key: string, value: string | null) { try { if (value === null) sessionStorage.removeItem(key); else sessionStorage.setItem(key, value) } catch { /* Storage may be unavailable; the current view still retains its draft. */ } }
function clearAccountStorage() { try { for (const key of Object.keys(sessionStorage)) if (key.startsWith('resumate:interview:')) sessionStorage.removeItem(key) } catch { /* No persisted state exists when storage is unavailable. */ } }
function persist() {
 if (!activeStorage || restoring) return
 storageWrite(`${activeStorage}:turn:${snapshot.value?.currentTurn}:draft`, draft.value || null)
 storageWrite(`${activeStorage}:pending`, pending.value ? JSON.stringify(pending.value) : null)
}
watch(draft, persist)
function restoreLocal(previousTurn: number | undefined) {
 if (!snapshot.value) return
 const nextStorage = `resumate:interview:${snapshot.value.userId}:${interviewId.value}`
 restoring = true
 if (nextStorage !== activeStorage) {
  activeStorage = nextStorage
  try { pending.value = JSON.parse(storageRead(`${activeStorage}:pending`) || 'null') } catch { pending.value = null }
 }
 if (previousTurn !== snapshot.value.currentTurn) draft.value = storageRead(`${activeStorage}:turn:${snapshot.value.currentTurn}:draft`) || ''
 restoring = false
}
function schedule() {
 clearTimeout(timer)
 if (snapshot.value?.status === 'active' && !snapshot.value.sessionInvalidated) timer = setTimeout(() => void refresh(false), 1500)
}
async function refresh(showLoading = true) {
 if (!auth.token || !interviewId.value) return
 const ownEpoch = epoch, requestNumber = ++readRequest
 if (showLoading) loading.value = true
 try {
  const result = await fetchInterview(interviewId.value)
  if (ownEpoch !== epoch || requestNumber !== readRequest) return
  const previousTurn = snapshot.value?.currentTurn
  snapshot.value = result; restoreLocal(previousTurn)
  readError.value = ''
 } catch (cause) { if (ownEpoch === epoch && requestNumber === readRequest) readError.value = message(cause) }
 finally { if (ownEpoch === epoch && requestNumber === readRequest) { loading.value = false; schedule() } }
}
async function deliverPending() {
 if (!pending.value || sending.value) return
 const command = structuredClone(toRaw(pending.value)), ownEpoch = epoch
 sending.value = true; error.value = ''
 try {
  await sendInterviewCommand(interviewId.value, command)
  if (ownEpoch !== epoch) return
  pending.value = null; finishing.value = false
  if (command.type === 'answer.submit') {
   storageWrite(`${activeStorage}:turn:${command.expectedTurn}:draft`, null)
   if (snapshot.value?.currentTurn === command.expectedTurn) draft.value = ''
  }
  persist(); await refresh(false)
 } catch (cause) {
  if (ownEpoch !== epoch) return
  error.value = message(cause)
  // A concrete rejection is known; transport errors retain the exact command for replay.
  if (cause instanceof AgentRunError && cause.status >= 400 && cause.status < 500 && cause.status !== 408) { pending.value = null; persist(); await refresh(false) }
 } finally { if (ownEpoch === epoch) sending.value = false }
}
function queue(command: InterviewCommand) { if (pending.value || sending.value) return; pending.value = command; persist(); void deliverPending() }
function submitAnswer() {
 if (!canAnswer.value || !draft.value.trim() || !snapshot.value) return
 queue({ clientMessageId: crypto.randomUUID(), type: 'answer.submit', expectedTurn: snapshot.value.currentTurn, payload: { text: draft.value.trim() } })
}
function issue(type: 'generation.cancel' | 'generation.retry' | 'session.finish') {
 if (!snapshot.value) return
 const base = { clientMessageId: crypto.randomUUID(), expectedTurn: snapshot.value.currentTurn }
 if (type === 'session.finish') queue({ ...base, type, payload: {} })
 else if (snapshot.value.generation) queue({ ...base, type, payload: { runId: snapshot.value.generation.runId } })
}
async function saveMemory(turn: InterviewTurn) {
 if (savingMemory.value) return
 const ownEpoch = epoch; savingMemory.value = true; error.value = ''
 try {
  const memory = await confirmInterviewMemory(interviewId.value, turn.turnIndex)
  if (ownEpoch !== epoch) return
  // A refresh may have replaced the captured turn while the confirmation was in flight.
  readRequest++; loading.value = false
  const currentTurn = snapshot.value?.turns.find(item => item.id === turn.id)
  if (currentTurn?.feedback) currentTurn.feedback.memoryId = memory.id
  memoryTurn.value = null; schedule()
 }
 catch (cause) { if (ownEpoch === epoch) error.value = message(cause) }
 finally { if (ownEpoch === epoch) savingMemory.value = false }
}
watch([interviewId, () => auth.token], (_value, previous) => {
 epoch++; clearTimeout(timer)
 if (previous && previous[1] !== undefined && previous[1] !== auth.token) clearAccountStorage()
 snapshot.value = null; draft.value = ''; pending.value = null; activeStorage = ''; error.value = ''; readError.value = ''
 loading.value = false; sending.value = false; savingMemory.value = false; memoryTurn.value = null; finishing.value = false
 void refresh()
}, { immediate: true })
onBeforeUnmount(() => { epoch++; clearTimeout(timer) })
</script>

<style scoped>
.interview-page { max-width: 1440px; margin-inline: auto; width: 100%; }
.interview-heading .section-head { align-items: flex-start; flex-wrap: wrap; gap: 16px; }
.interview-heading .section-head > div { flex: 1 1 24rem; min-width: 0; }
.interview-eyebrow { color: var(--color-primary); font-size: 13px; font-weight: 650; margin: 0 0 8px; }
.interview-source { display: flex; flex-wrap: wrap; gap: 8px 24px; padding-top: 16px; margin-top: 20px; border-top: 1px solid var(--color-border); font-size: 13px; color: var(--color-text-secondary); }
.interview-source strong { width: 100%; color: var(--color-text); }
.interview-progress { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; justify-content: space-between; }
.interview-progress p { margin: 6px 0 0; color: var(--color-text-secondary); font-size: 13px; }
.interview-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.interview-columns { display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr); gap: 24px; align-items: start; }
.interview-current { grid-column: 2; grid-row: 1; } .interview-history { grid-column: 1; grid-row: 1; }
.interview-page :is(h3,h4,h5,p,blockquote,strong,span,small) { overflow-wrap: anywhere; }
.interview-page :is(p,blockquote) { line-height: 1.75; }
.interview-question { font-size: 18px; white-space: pre-wrap; margin: 24px 0; }
.interview-current form { margin-top: 24px; }
.interview-current textarea { width: 100%; min-width: 0; resize: vertical; min-height: 192px; line-height: 1.75; }
.interview-answer-foot { display: flex; flex-wrap: wrap; gap: 12px; justify-content: space-between; align-items: center; margin-top: 12px; }
.interview-answer-foot small,.interview-muted { color: var(--color-text-secondary); }
.interview-notice { margin: 0; padding: 16px; border-radius: var(--radius-sm); background: var(--surface-panel-muted); }
.interview-turn + .interview-turn { border-top: 1px solid var(--color-border); margin-top: 24px; padding-top: 24px; }
.interview-turn h4 { margin: 8px 0; font-size: 15px; line-height: 1.75; }
.interview-answer { margin: 20px 0; } .interview-answer > strong { font-size: 13px; color: var(--color-text-secondary); }
.interview-answer p { white-space: pre-wrap; margin: 8px 0; }
.interview-feedback h5 { font-size: 13px; margin: 20px 0 8px; }
.interview-feedback ul { padding-left: 20px; } .interview-feedback li + li { margin-top: 12px; }
.interview-focus { border-left: 3px solid var(--color-primary-border); padding: 2px 0 2px 16px; margin: 20px 0; }
.interview-focus p { margin: 6px 0; }
.interview-confirm { width: 100%; margin-top: 16px; padding: 16px; background: var(--color-primary-light); border-radius: var(--radius-sm); }
.interview-confirm > button + button { margin-left: 8px; }
.interview-page :deep(blockquote) { margin: 12px 0; padding-left: 12px; border-left: 2px solid var(--color-primary-border); white-space: pre-wrap; overflow-wrap: anywhere; }
.interview-page :deep(.interview-references) { font-size: 13px; color: var(--color-text-secondary); margin: 12px 0; }
.interview-page :deep(.interview-references summary) { cursor: pointer; min-height: 32px; display: list-item; }
.interview-page :deep(.interview-references p) { margin: 4px 0; }
@media (max-width: 1100px) { .interview-columns { grid-template-columns: minmax(0, 1fr); gap: 16px; } .interview-current,.interview-history { grid-column: 1; grid-row: auto; } }
@media (max-width: 768px) { .interview-heading .section-head > div { flex-basis: auto; } }
@media (max-width: 480px) { .interview-answer-foot > button { width: 100%; } .interview-question { font-size: 16px; } .interview-source { gap: 8px; } }
</style>

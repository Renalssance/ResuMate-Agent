<template>
  <section class="chat-workspace" :class="{ 'is-empty': auth.isAuthenticated && !detail?.turns.length && !loading }" aria-label="求职对话工作台">
    <details ref="historyMenu" class="chat-history">
      <summary><MessageCircle :size="16" /><span>我的对话</span><ChevronDown :size="14" class="history-chevron" /></summary>
      <div class="history-popover" aria-label="会话列表">
        <div class="history-heading"><span>最近对话</span><button type="button" :disabled="sending" @click="newChat"><Plus :size="15" /> 新对话</button></div>
        <p v-if="!auth.isAuthenticated" class="history-note">登录后保存对话。</p>
        <p v-else-if="!sessions.length" class="history-note">还没有对话。</p>
        <nav v-else class="session-list"><RouterLink v-for="item in sessions" :key="item.sessionId" :to="`/chat/${item.sessionId}`" :aria-current="currentId === item.sessionId ? 'page' : undefined" @click="closeHistory"><MessageCircle :size="15" /><span>{{ item.title || '新的求职对话' }}</span></RouterLink></nav>
        <RouterLink class="history-docs" to="/documents" @click="closeHistory"><Files :size="15" /> 管理文档</RouterLink>
      </div>
    </details>
    <div class="chat-main">
      <div ref="conversation" class="chat-conversation" @scroll="trackScroll">
        <div v-if="!auth.isAuthenticated" class="chat-welcome"><h3>你好，我是米洛。</h3><p>登录后，我们可以一起分析岗位、准备简历和练习面试。</p><RouterLink class="chat-primary" to="/login">登录并开始</RouterLink></div>
        <p v-else-if="loading" class="chat-notice" role="status">正在读取对话…</p>
        <div v-else-if="!detail?.turns.length" class="chat-welcome"></div>
        <div v-else class="chat-turns">
          <article v-for="turn in detail.turns" :key="turn.runId" class="chat-turn">
            <div class="user-message"><span class="message-author">你</span><p>{{ turn.message }}</p></div>
            <div class="assistant-message"><div class="assistant-label"><Cat :size="19" /><strong>米洛</strong><span v-if="!terminal(turn.status)" role="status">{{ turnLabel(turn.status) }}</span></div>
              <div v-if="turn.tools.length || turn.text || turn.result?.text || !terminal(turn.status)" :class="['assistant-response', { 'is-empty': !turn.tools.length && !turn.text && !turn.result?.text }]">
                <details v-if="turn.tools.length" class="chat-process" :open="!turn.result?.text">
                  <summary><span>{{ processSummary(turn) }}</span><ChevronDown :size="13" class="process-chevron" /></summary>
                  <ul class="chat-tools" aria-label="工具执行进度"><li v-for="tool in turn.tools" :key="tool.operationKey"><span :class="['tool-dot', tool.status]" aria-hidden="true"></span><span>{{ toolLabel(tool.name) }}</span><small>{{ tool.status === 'running' ? '正在执行' : tool.status === 'failed' ? '未完成' : '已执行' }}</small></li></ul>
                </details>
                <MarkdownContent class="assistant-text" :content="turn.result?.text || turn.text" :streaming="!terminal(turn.status)" />
              </div>
              <ChatTaskCard v-for="reference in runReferences(turn)" :key="reference" :reference="reference" @continue="usePrompt" />
              <div v-for="reference in businessReferences(turn)" :key="reference" class="business-reference"><RouterLink :to="referenceLink(reference)">{{ referenceLabel(reference) }} <ArrowUpRight :size="14" /></RouterLink></div>
              <p v-if="turn.status === 'failed'" class="chat-failure" role="alert">{{ failureText(turn.errorCode) }}<RouterLink to="/settings">检查模型设置</RouterLink><button type="button" :disabled="sending || Boolean(activeTurn)" @click="changeRun(turn.runId, 'retry')">重试回复</button></p>
              <p v-if="turn.status === 'cancelled'" class="chat-muted">本轮已停止。</p>
              <RouterLink v-if="['waiting_input', 'waiting_approval'].includes(turn.status)" :to="`/agent/tasks/${turn.runId}`">{{ turn.status === 'waiting_input' ? '补充信息并继续' : '前往审阅' }}</RouterLink>
            </div>
          </article>
        </div>
      </div>
      <div v-if="auth.isAuthenticated" class="composer-wrap">
        <p v-if="error" class="chat-error" role="alert">{{ error }}<button v-if="currentId && !detail" type="button" @click="openSession(currentId)">重新读取</button></p>
        <p v-if="disconnected" class="chat-notice" role="status">连接已断开，正在重连。任务会继续运行。</p>
        <form class="chat-composer" @submit.prevent="send">
          <textarea ref="messageField" v-model="draft" aria-label="给米洛的消息" rows="1" placeholder="问点什么，和米洛一起梳理…" :disabled="sending" @keydown="composerKeydown"></textarea>
          <div class="composer-footer">
            <div class="context-controls">
              <ChatMaterialPicker
                v-model:resume-id="resumeId"
                v-model:job-id="jdId"
                :resumes="documents.parsedResumes"
                :jobs="documents.parsedJds"
                :import-state="importState"
                :pending-action="pendingImportAction"
                :import-error="importError"
                @local-file="startImport"
                @confirm-type="confirmDocumentType"
              />
            </div>
            <button v-if="activeTurn" class="stop-button" type="button" :disabled="sending" @click="changeRun(activeTurn.runId, 'cancel')"><Square :size="12" /> 停止</button>
            <button v-else class="send-button" type="submit" :disabled="!draft.trim() || sending || loading || importBusy" aria-label="发送消息"><ArrowUp :size="19" /></button>
          </div>
        </form>
        <div v-if="!detail?.turns.length && !loading" class="chat-suggestions"><button v-for="suggestion in suggestions" :key="suggestion.prompt" type="button" @click="usePrompt(suggestion.prompt)">{{ suggestion.label }}<ArrowUpRight :size="15" /></button></div>
      </div>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowUp, ArrowUpRight, Cat, ChevronDown, Files, MessageCircle, Plus, Square } from '@lucide/vue'
import { createChatSession, fetchChatSession, fetchChatSessions, sendChatMessage, type ChatDetail, type ChatSession, type ChatTurn } from '../api/chat'
import { cancelAgentRun, retryAgentRun } from '../api/agentRuns'
import { useDocumentImport } from '../composables/useDocumentImport'
import { subscribeRun, type RunSnapshot, type RunStatus, type RunSubscription } from '../services/agentStream'
import { useAuthStore } from '../stores/auth'
import { useDocumentStore } from '../stores/document'
import MarkdownContent from '../components/chat/MarkdownContent.vue'
import ChatTaskCard from '../components/chat/ChatTaskCard.vue'
import ChatMaterialPicker from '../components/chat/ChatMaterialPicker.vue'
const route = useRoute(), router = useRouter(), auth = useAuthStore(), documents = useDocumentStore()
const sessions = ref<ChatSession[]>([]), detail = ref<ChatDetail | null>(null), currentId = ref('')
const draft = ref(''), resumeId = ref(''), jdId = ref(''), loading = ref(false), sending = ref(false), error = ref(''), disconnected = ref(false)
const importScope = computed(() => `chat:${String(route.params.sessionId || currentId.value || 'new')}`)
const {
  state: importState, pendingAction: pendingImportAction, resultDocument: importedDocument,
  error: importError, startImport, confirmDocumentType,
} = useDocumentImport(importScope)
const importBusy = computed(() => ['uploading', 'processing'].includes(importState.value))
const conversation = ref<HTMLElement | null>(null), messageField = ref<HTMLTextAreaElement | null>(null)
const historyMenu = ref<HTMLDetailsElement | null>(null)
const suggestions = [
  { label: '看看简历方向', prompt: '帮我看看简历适合什么岗位' },
  { label: '分析岗位匹配', prompt: '分析我和目标岗位的匹配度' },
  { label: '准备模拟面试', prompt: '陪我准备下一场面试' },
]
const terminal = (status: string) => ['succeeded', 'failed', 'cancelled'].includes(status)
const activeTurn = computed(() => [...(detail.value?.turns || [])].reverse().find(turn => !terminal(turn.status)))
let subscription: RunSubscription | undefined, generation = 0, connectedRunId = '', nearBottom = true
let intent: { key: string; requestId: string } | undefined
function trackScroll() { const el = conversation.value; nearBottom = !el || el.scrollHeight - el.scrollTop - el.clientHeight < 100 }
async function scrollDown() { await nextTick(); if (nearBottom && conversation.value) conversation.value.scrollTop = conversation.value.scrollHeight }
function fail(cause: unknown) { error.value = cause instanceof Error ? cause.message : '请求失败，请重试' }
async function loadSessions() { const token = auth.token; try { const value = await fetchChatSessions(); if (auth.token === token) sessions.value = value } catch (cause) { if (auth.token === token) fail(cause) } }
function disconnect() { generation++; subscription?.close(); subscription = undefined; connectedRunId = ''; disconnected.value = false }
async function reload(epoch = generation) {
  const id = currentId.value
  if (!id) return
  const value = await fetchChatSession(id)
  if (epoch !== generation || currentId.value !== id) return
  const currentTurns = detail.value?.turns || []
  value.turns = value.turns.map(turn => { const current = detail.value?.turns.find(item => item.runId === turn.runId); return current && current.lastSeq > turn.lastSeq ? current : turn })
  const receivedIds = new Set(value.turns.map(turn => turn.runId))
  value.turns.push(...currentTurns.filter(turn => !receivedIds.has(turn.runId)))
  detail.value = value; void loadSessions(); void scrollDown()
}
async function openSession(id: string) {
  disconnect(); currentId.value = id; detail.value = null; error.value = ''; nearBottom = true
  resumeId.value = ''; jdId.value = ''
  const epoch = generation; loading.value = Boolean(id)
  if (!id || !auth.isAuthenticated) { loading.value = false; return }
  try {
    await reload(epoch)
    if (epoch === generation) {
      const input = (detail.value as ChatDetail | null)?.turns.at(-1)?.input
      resumeId.value = input?.resumeId ? `resume:${input.resumeId}` : ''
      jdId.value = input?.jdId ? `jd:${input.jdId}` : ''
      connectTurn()
    }
  }
  catch (cause) { if (epoch === generation) fail(cause) }
  finally { if (epoch === generation) { loading.value = false; void scrollDown() } }
}
function connectTurn() {
  const turn = activeTurn.value
  if (!turn || connectedRunId === turn.runId) return
  subscription?.close(); connectedRunId = turn.runId
  const epoch = generation
  const accept = (snapshot: RunSnapshot) => {
    if (epoch !== generation) return
    const row = detail.value?.turns.find(item => item.runId === snapshot.runId)
    if (!row) return
    row.status = snapshot.status
    if (terminal(snapshot.status)) void reload(epoch).catch(fail)
  }
  subscription = subscribeRun({ runId: turn.runId, after: turn.lastSeq, onSnapshot: accept,
    onReset: () => { if (epoch === generation) void reload(epoch).catch(fail) },
    onConnected: snapshot => { if (epoch === generation) { disconnected.value = false; accept(snapshot) } },
    onEvent: event => {
      if (epoch !== generation) return
      const row = detail.value?.turns.find(item => item.runId === event.runId)
      if (!row || event.seq <= row.lastSeq) return
      row.lastSeq = event.seq; disconnected.value = false
      if (event.type === 'assistant.delta') row.text += String(event.payload.text || '')
      if (event.type.startsWith('tool.')) {
        const key = String(event.payload.operation_key || ''), tool = row.tools.find(item => item.operationKey === key)
        const value = { name: String(event.payload.tool_name || ''), operationKey: key, status: (event.type === 'tool.started' ? 'running' : event.type === 'tool.failed' ? 'failed' : 'succeeded') as 'running' | 'failed' | 'succeeded', resultRef: event.payload.result_ref ? String(event.payload.result_ref) : null }
        if (tool) Object.assign(tool, value); else row.tools.push(value)
      }
      if (event.type === 'run.status') { row.status = event.payload.status as RunStatus; if (terminal(row.status)) void reload(epoch).catch(fail) }
      void scrollDown()
    }, onError: cause => { if (epoch === generation) { disconnected.value = true; if ('status' in cause && [401, 403, 404].includes(Number(cause.status))) fail(cause) } },
  })
}
function closeHistory() { historyMenu.value?.removeAttribute('open') }
async function newChat() { if (sending.value) return; closeHistory(); draft.value = ''; intent = undefined; await router.push('/chat'); if (currentId.value) await openSession(''); await nextTick(); messageField.value?.focus() }
async function usePrompt(message: string) { draft.value = message; await nextTick(); messageField.value?.focus() }
function composerKeydown(event: KeyboardEvent) { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && !window.matchMedia('(pointer: coarse)').matches) { event.preventDefault(); void send() } }
async function send() {
  if (!draft.value.trim() || sending.value || activeTurn.value || importBusy.value || loading.value) return
  const message = draft.value.trim(), token = auth.token
  sending.value = true; error.value = ''
  try {
    if (!currentId.value) {
      const created = await createChatSession(); if (auth.token !== token) return
      currentId.value = created.sessionId; detail.value = { ...created, turns: [] }; sessions.value.unshift(created)
      await router.replace(`/chat/${created.sessionId}`)
    }
    const id = currentId.value, epoch = generation
    const key = JSON.stringify([id, message, resumeId.value, jdId.value])
    if (intent?.key !== key) intent = { key, requestId: crypto.randomUUID() }
    const result = await sendChatMessage(id, { message, requestId: intent.requestId, ...(resumeId.value ? { resumeId: Number(resumeId.value.split(':').pop()) } : {}), ...(jdId.value ? { jdId: Number(jdId.value.split(':').pop()) } : {}) })
    if (epoch !== generation || token !== auth.token) return
    intent = undefined; draft.value = ''; nearBottom = true
    detail.value!.turns.push({ runId: result.runId, message, status: result.status, text: '', lastSeq: 0, tools: [], outputRefs: [], result: null, errorCode: null })
    connectTurn(); void loadSessions(); void scrollDown()
  } catch (cause) { if (auth.token === token) fail(cause) }
  finally { sending.value = false }
}
async function changeRun(id: string, operation: 'retry' | 'cancel') {
  if (sending.value) return
  const epoch = generation; sending.value = true; error.value = ''
  try { await (operation === 'retry' ? retryAgentRun(id) : cancelAgentRun(id)); if (epoch !== generation) return; await reload(epoch); if (epoch === generation) { connectedRunId = ''; connectTurn() } }
  catch (cause) { if (epoch === generation) fail(cause) }
  finally { sending.value = false }
}
function references(turn: ChatTurn) { return [...new Set([...turn.tools.map(tool => tool.resultRef).filter((ref): ref is string => Boolean(ref)), ...turn.outputRefs.map(ref => `${ref.type}:${ref.id}`)])] }
function runReferences(turn: ChatTurn) { return references(turn).filter(ref => ref.startsWith('run:')) }
function businessReferences(turn: ChatTurn) { return references(turn).filter(ref => /^(interview|application|jd):/.test(ref)) }
function referenceLink(ref: string) { const [kind, id] = ref.split(':'); return kind === 'interview' ? `/interviews/${id}` : kind === 'application' ? '/applications' : '/jobs' }
function referenceLabel(ref: string) { return ref.startsWith('interview:') ? '进入模拟面试' : ref.startsWith('application:') ? '查看投递记录' : '查看收藏岗位' }
function turnLabel(status: RunStatus) { return ({ queued: '等待回复', running: '正在思考', waiting_input: '等待补充信息', waiting_approval: '等待审阅', succeeded: '已回复', failed: '回复失败', cancelled: '已停止' })[status] }
function failureText(code: string | null) {
  if (code === 'model_context_not_configured') return '请先在模型设置中填写上下文容量，再重试回复。'
  if (code === 'context_budget_exceeded') return '本轮资料超出模型容量，请减少资料或核对模型设置后重试。'
  if (code === 'session_context_invalidated') return '本轮使用的记忆已删除，请开启新对话继续。'
  return '回复未完成，可以检查模型设置后重试。'
}
function toolLabel(name: string) { return ({ list_documents: '查看文档', read_document: '读取文档', start_task: '提交求职任务', get_task: '读取任务结果', answer_task: '提交补充信息', save_job: '收藏岗位', list_applications: '查看投递记录', record_application: '记录投递', update_application_status: '更新投递进展', start_interview: '开启面试', get_interview: '读取面试进度', answer_interview: '提交面试回答' } as Record<string, string>)[name] || '处理求职资料' }
function processSummary(turn: ChatTurn) {
  const first = turn.tools[0]
  if (!first) return '处理记录'
  return turn.tools.length > 1 ? `${toolLabel(first.name)}等 ${turn.tools.length} 项` : toolLabel(first.name)
}

watch([importedDocument, loading], ([document, readingHistory]) => {
  if (!document || readingHistory) return
  documents.upsertDocuments([document])
  if (document.type === 'resume') resumeId.value = document.id
  else jdId.value = document.id
})
watch([() => route.params.sessionId, () => auth.token], ([id, token], previous) => {
  const sessionId = String(id || '')
  if (previous && previous[1] !== token) { disconnect(); sessions.value = []; detail.value = null; currentId.value = ''; draft.value = ''; resumeId.value = ''; jdId.value = ''; intent = undefined }
  if (token) { if (!previous || previous[1] !== token) { void loadSessions(); void documents.loadDocuments() }; if (sessionId !== currentId.value || !detail.value) void openSession(sessionId) }
  else { disconnect(); currentId.value = ''; detail.value = null }
}, { immediate: true })
onBeforeUnmount(disconnect)
</script>
<style scoped>
.chat-workspace {
  --composer-lift: 40px;
  --composer-clearance: 42px;
  position: relative;
  min-height: 650px;
  height: calc(100dvh - 164px);
  max-height: 1100px;
  color: #594334;
  background: transparent;
}
.chat-main {
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.chat-history {
  position: absolute;
  top: 18px;
  left: 18px;
  z-index: 5;
}
.chat-history summary {
  width: max-content;
  min-height: 40px;
  padding: 8px 13px;
  display: flex;
  align-items: center;
  gap: 8px;
  list-style: none;
  cursor: pointer;
  color: #795f4a;
  font-size: 12px;
  background: rgba(255, 253, 249, .62);
  border: 1px solid rgba(158, 126, 97, .22);
  border-radius: 13px;
  box-shadow: 0 8px 28px rgba(85, 59, 40, .06);
  backdrop-filter: blur(18px) saturate(125%);
  -webkit-backdrop-filter: blur(18px) saturate(125%);
}
.chat-history summary::-webkit-details-marker { display: none; }
.history-chevron { transition: transform .18s ease; }
.chat-history[open] .history-chevron { transform: rotate(180deg); }
.history-popover {
  width: min(290px, calc(100vw - 330px));
  max-height: min(520px, calc(100dvh - 240px));
  margin-top: 9px;
  padding: 15px;
  display: flex;
  flex-direction: column;
  gap: 15px;
  overflow: auto;
  background: rgba(255, 252, 246, .9);
  border: 1px solid rgba(158, 126, 97, .2);
  border-radius: 16px;
  box-shadow: 0 18px 48px rgba(85, 59, 40, .12);
  backdrop-filter: blur(24px) saturate(125%);
  -webkit-backdrop-filter: blur(24px) saturate(125%);
}
.history-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 0 2px;
  color: #9a806b;
  font-size: 11px;
}
.history-heading button {
  min-height: 32px;
  padding: 5px 9px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #70523c;
  background: rgba(255, 255, 255, .55);
  border: 1px solid #e4d6c6;
  border-radius: 9px;
  font-size: 11px;
}
.history-note {
  margin: 0;
  padding: 5px 2px;
  color: #9a806b;
  font-size: 12px;
}
.session-list {
  display: grid;
  gap: 5px;
}
.session-list a {
  min-width: 0;
  padding: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #896c55;
  border-radius: 9px;
  text-decoration: none;
  font-size: 12px;
}
.session-list a[aria-current="page"] {
  color: #594334;
  background: rgba(234, 220, 203, .76);
}
.session-list span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-list svg { flex-shrink: 0; }
.history-docs {
  padding: 12px 2px 0;
  display: flex;
  align-items: center;
  gap: 7px;
  color: #8b715e;
  border-top: 1px solid rgba(158, 126, 97, .16);
  text-decoration: none;
  font-size: 11px;
}
.chat-conversation {
  flex: 1;
  min-height: 0;
  padding: 78px max(34px, calc((100% - 820px) / 2)) calc(24px + var(--composer-clearance));
  overflow: auto;
  overscroll-behavior: contain;
}
.is-empty .chat-main {
  justify-content: center;
}
.is-empty .chat-conversation {
  display: none;
}
.chat-welcome {
  min-height: 100%;
  display: grid;
  place-items: center;
  text-align: center;
}
.chat-welcome h3 {
  margin: 0 0 12px;
  font-size: 22px;
  font-weight: 500;
}
.chat-welcome p {
  margin: 0 0 24px;
  color: #9a806b;
  font-size: 13px;
  line-height: 1.8;
}
.chat-primary {
  padding: 11px 18px;
  color: #fff;
  background: #785537;
  border-radius: 10px;
  text-decoration: none;
}
.chat-turns {
  max-width: 820px;
  margin: 0 auto;
}
.chat-turn {
  display: grid;
  gap: 28px;
  margin-bottom: 38px;
}
.user-message {
  align-self: end;
  justify-self: end;
  max-width: 85%;
}
.message-author {
  display: block;
  margin-bottom: 8px;
  color: #ac9078;
  font-size: 10px;
  text-align: right;
}
.user-message p {
  margin: 0;
  padding: 14px 18px;
  color: #594334;
  background: rgba(238, 225, 207, .88);
  border-radius: 16px 16px 4px 16px;
  font-size: 14px;
  line-height: 1.8;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.assistant-message {
  min-width: 0;
  display: grid;
  gap: 12px;
}
.assistant-label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #8d6747;
  font-size: 12px;
}
.assistant-label > span {
  margin-left: 4px;
  color: #ad9178;
  font-size: 11px;
}
.assistant-response {
  padding: 17px 19px 18px;
  background: rgba(255, 253, 249, .68);
  border: 1px solid rgba(158, 126, 97, .16);
  border-radius: 5px 19px 19px 19px;
  box-shadow:
    0 12px 34px rgba(85, 59, 40, .055),
    inset 0 1px 0 rgba(255, 255, 255, .7);
  backdrop-filter: blur(18px) saturate(116%);
  -webkit-backdrop-filter: blur(18px) saturate(116%);
}
.assistant-response.is-empty { display: none; }
.assistant-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.95;
  overflow-wrap: anywhere;
}
.assistant-text :deep(> :first-child) { margin-top: 0; }
.assistant-text :deep(> :last-child) { margin-bottom: 0; }
.assistant-text :deep(p) { margin: 0 0 11px; }
.assistant-text :deep(h1),
.assistant-text :deep(h2),
.assistant-text :deep(h3),
.assistant-text :deep(h4) {
  margin: 20px 0 9px;
  color: #4f3a2c;
  line-height: 1.4;
  letter-spacing: -.01em;
}
.assistant-text :deep(h1) { font-size: 20px; }
.assistant-text :deep(h2) { font-size: 17px; }
.assistant-text :deep(h3) { font-size: 15px; }
.assistant-text :deep(h4) { font-size: 14px; }
.assistant-text :deep(ul),
.assistant-text :deep(ol) {
  margin: 8px 0 13px;
  padding-left: 1.55em;
}
.assistant-text :deep(li + li) { margin-top: 4px; }
.assistant-text :deep(li > p) { margin: 0; }
.assistant-text :deep(strong) { color: #4f392b; font-weight: 650; }
.assistant-text :deep(a) {
  color: #795337;
  text-decoration-color: rgba(121, 83, 55, .34);
  text-underline-offset: 3px;
}
.assistant-text :deep(blockquote) {
  margin: 12px 0;
  padding: 3px 0 3px 14px;
  color: #806956;
  border-left: 2px solid rgba(143, 108, 75, .34);
}
.assistant-text :deep(code) {
  padding: .12em .36em;
  color: #6c4931;
  background: rgba(225, 207, 184, .48);
  border-radius: 5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: .9em;
}
.assistant-text :deep(pre) {
  margin: 13px 0;
  padding: 14px 15px;
  overflow: auto;
  color: #f8efe5;
  background: #5a4638;
  border-radius: 12px;
  line-height: 1.65;
}
.assistant-text :deep(pre code) { padding: 0; color: inherit; background: transparent; }
.assistant-text :deep(hr) {
  margin: 17px 0;
  border: 0;
  border-top: 1px solid rgba(158, 126, 97, .18);
}
.assistant-text :deep(table) {
  width: 100%;
  margin: 13px 0;
  border-collapse: collapse;
  font-size: 12px;
}
.assistant-text :deep(th),
.assistant-text :deep(td) {
  padding: 8px 9px;
  border-bottom: 1px solid rgba(158, 126, 97, .16);
  text-align: left;
}
.assistant-text :deep(img) { max-width: 100%; border-radius: 10px; }
.assistant-text :deep(.stream-char) {
  display: inline-block;
  will-change: transform, opacity;
  animation: stream-char-rise 180ms cubic-bezier(.23, 1, .32, 1) both;
}
@keyframes stream-char-rise {
  from { opacity: .18; transform: translateY(.28em); }
  to { opacity: 1; transform: translateY(0); }
}
.chat-process {
  margin-bottom: 14px;
  padding-bottom: 12px;
  color: #9a806b;
  border-bottom: 1px solid rgba(158, 126, 97, .14);
  font-size: 11px;
}
.chat-process summary {
  width: max-content;
  max-width: 100%;
  min-height: 24px;
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  list-style: none;
}
.chat-process summary::-webkit-details-marker { display: none; }
.process-chevron { flex-shrink: 0; transition: transform .18s ease; }
.chat-process[open] .process-chevron { transform: rotate(180deg); }
.chat-process[open] summary { margin-bottom: 9px; }
.chat-tools {
  margin: 0;
  padding: 0 2px;
  display: grid;
  gap: 7px;
  color: #9a806b;
  list-style: none;
  font-size: 11px;
}
.chat-tools li {
  display: flex;
  align-items: center;
  gap: 9px;
}
.chat-tools small {
  margin-left: auto;
  color: #ae9682;
}
.tool-dot {
  width: 6px;
  height: 6px;
  background: #b5905c;
  border-radius: 50%;
}
.tool-dot.succeeded { background: #769276; }
.tool-dot.failed { background: #b4614e; }
.business-reference a {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #805d40;
  font-size: 13px;
}
.composer-wrap {
  position: relative;
  z-index: 3;
  width: min(100%, 900px);
  margin: calc(-1 * var(--composer-lift)) auto 0;
  padding: 10px 34px 20px;
  flex-shrink: 0;
}
.is-empty .composer-wrap {
  margin-top: 0;
  padding-bottom: 8vh;
}
.chat-composer {
  min-height: 58px;
  padding: 7px 8px 7px 17px;
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(255, 253, 249, .64);
  border: 1px solid rgba(158, 126, 97, .28);
  border-radius: 999px;
  box-shadow:
    0 22px 60px rgba(85, 59, 40, .1),
    inset 0 1px 0 rgba(255, 255, 255, .68);
  backdrop-filter: blur(24px) saturate(130%);
  -webkit-backdrop-filter: blur(24px) saturate(130%);
  transition: border-color .18s ease, box-shadow .18s ease;
}
.chat-composer:focus-within {
  border-color: rgba(138, 98, 65, .56);
  box-shadow:
    0 24px 64px rgba(85, 59, 40, .12),
    0 0 0 3px rgba(120, 85, 55, .05),
    inset 0 1px 0 rgba(255, 255, 255, .72);
}
.chat-composer textarea {
  width: auto;
  min-width: 90px;
  min-height: 34px;
  max-height: 144px;
  padding: 5px 0;
  display: block;
  flex: 1 1 auto;
  resize: none;
  overflow-y: auto;
  field-sizing: content;
  color: #594334;
  background: transparent;
  border: 0;
  border-radius: 0;
  outline: 0;
  box-shadow: none;
  font: inherit;
  font-size: 15px;
  line-height: 1.6;
}
.chat-composer textarea::placeholder { color: #aa907b; }
.composer-footer {
  min-width: 0;
  display: flex;
  align-items: center;
  flex: 0 0 auto;
  gap: 10px;
}
.context-controls {
  min-width: 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.context-controls :deep(.material-chips) { min-width: 0; display: flex; gap: 6px; }
.context-controls :deep(.material-chip) {
  max-width: 190px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.send-button {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  color: #fff7eb;
  background: #785537;
  border: 0;
  border-radius: 50%;
}
.send-button:disabled { background: #d7c6b0; }
.stop-button {
  min-height: 38px;
  padding: 8px 13px;
  display: flex;
  align-items: center;
  gap: 6px;
  color: #785537;
  background: rgba(244, 233, 217, .82);
  border: 0;
  border-radius: 12px;
  white-space: nowrap;
}
.chat-suggestions {
  width: 100%;
  margin-top: 18px;
  display: flex;
  justify-content: center;
  gap: 10px;
}
.chat-suggestions button {
  min-height: 40px;
  padding: 8px 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex: 0 1 auto;
  color: #795f4a;
  background: rgba(255, 253, 249, .5);
  border: 1px solid rgba(158, 126, 97, .22);
  border-radius: 999px;
  font-size: 11px;
  white-space: nowrap;
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}
.chat-suggestions button:hover {
  color: #594334;
  background: rgba(255, 253, 249, .8);
  border-color: rgba(138, 98, 65, .38);
}
.chat-error,
.chat-failure {
  color: #a04432;
  font-size: 13px;
  line-height: 1.7;
}
.chat-error button,
.chat-failure button {
  min-height: 34px;
  margin-left: 12px;
  color: inherit;
  background: transparent;
  border: 0;
  text-decoration: underline;
}
.chat-notice,
.chat-muted {
  color: #9b7a59;
  font-size: 12px;
  line-height: 1.8;
}
button { cursor: pointer; }
button:disabled { cursor: default; opacity: .65; }
a:focus-visible,
button:focus-visible,
summary:focus-visible {
  outline: 2px solid #ac8965;
  outline-offset: 3px;
}
@media (prefers-reduced-motion: reduce) {
  .history-chevron,
  .process-chevron,
  .chat-composer { transition: none; }
  .assistant-text :deep(.stream-char) { animation: stream-char-fade 120ms cubic-bezier(.23, 1, .32, 1) both; }
  @keyframes stream-char-fade {
    from { opacity: .35; }
    to { opacity: 1; }
  }
}
@media (max-width: 1100px) {
  .history-popover { width: min(280px, calc(100vw - 250px)); }
  .chat-conversation { padding-left: 24px; padding-right: 24px; }
  .composer-wrap { padding-left: 24px; padding-right: 24px; }
}
@media (max-width: 720px) {
  .chat-workspace {
    --composer-lift: 32px;
    --composer-clearance: 34px;
    height: calc(100dvh - 138px);
    min-height: 560px;
  }
  .chat-history { top: 10px; left: 10px; }
  .chat-history summary { min-height: 36px; padding: 7px 10px; }
  .history-popover {
    width: min(290px, calc(100vw - 38px));
    max-height: min(430px, calc(100dvh - 210px));
  }
  .chat-conversation { padding: 62px 18px calc(18px + var(--composer-clearance)); }
  .composer-wrap { padding: 8px 12px 14px; }
  .is-empty .composer-wrap { padding-bottom: 4vh; }
  .chat-composer {
    min-height: 54px;
    padding: 9px 9px 8px 14px;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 5px 8px;
    border-radius: 24px;
  }
  .chat-composer textarea {
    width: 100%;
    min-width: 0;
    min-height: 32px;
    grid-column: 1;
    grid-row: 1;
    font-size: 14px;
  }
  .composer-footer { display: contents; }
  .context-controls {
    min-width: 0;
    grid-column: 1 / -1;
    grid-row: 2;
    gap: 5px;
  }
  .context-controls :deep(.material-picker) {
    width: 100%;
    display: grid;
    grid-template-columns: minmax(0, 1fr) 38px minmax(0, 1fr);
  }
  .context-controls :deep(.material-chips) { display: contents; }
  .context-controls :deep(.material-chip) { max-width: min(100%, 132px); grid-row: 1; }
  .context-controls :deep(.material-chip:first-child) { grid-column: 1; justify-self: end; }
  .context-controls :deep(.material-chip:nth-child(2)) { grid-column: 3; justify-self: start; }
  .context-controls :deep(.material-anchor) { grid-column: 2; grid-row: 1; }
  .send-button,
  .stop-button {
    grid-column: 2;
    grid-row: 1;
    align-self: center;
  }
  .send-button { width: 36px; height: 36px; }
  .chat-suggestions {
    flex-wrap: wrap;
    padding: 0 2px;
  }
  .chat-suggestions button { flex: 0 0 auto; padding-inline: 12px; }
  .chat-turn { gap: 24px; }
  .user-message { max-width: 92%; }
  .assistant-response { padding: 15px 16px 16px; border-radius: 4px 17px 17px 17px; }
}
</style>

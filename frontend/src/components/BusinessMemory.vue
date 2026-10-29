<template>
  <section class="card workflow-card business-memory" aria-label="偏好与面试记忆">
    <div class="section-head">
      <div><h2>偏好与面试记忆</h2><p>保存你希望下次准备材料时记住的偏好和反馈。</p></div>
      <button class="button-secondary" type="button" :disabled="loading || busy || !auth.token" @click="loadMemories">刷新记忆状态</button>
    </div>
    <p v-if="!auth.token" class="muted-note">登录后添加和查看你的记忆。</p>
    <template v-else>
      <div class="memory-workspace">
        <form class="memory-form" @submit.prevent="save">
          <label><span>记忆类型</span><select v-model="kind" aria-label="记忆类型" :disabled="busy"><option value="preference">求职偏好</option><option value="interview_feedback">面试反馈</option></select></label>
          <label><span>记忆内容</span><textarea v-model="content" aria-label="记忆内容" rows="4" maxlength="4000" required :disabled="busy" placeholder="如：希望突出后端工程方向；回答问题时先说明我的职责。" /></label>
          <p class="memory-hint">仅用于调整表达和准备重点；记忆不能作为经历证据。</p>
          <label class="memory-confirm"><input v-model="confirmed" type="checkbox" data-memory-confirm :disabled="busy" />我已核对，确认保存这条记忆</label>
          <div class="memory-actions"><button class="button-primary" type="submit" :disabled="loading || busy || !confirmed || !content.trim()">{{ saving ? '正在保存…' : '保存记忆' }}</button><span class="muted-note">保存后，从下一次新任务起使用。</span></div>
        </form>
        <div class="memory-collection">
          <div class="memory-list-head"><h3>已保存记忆</h3><span>{{ items.length }} 条</span></div>
          <p v-if="loading" class="muted-note" role="status">正在读取记忆…</p>
          <p v-else-if="!items.length && !error" class="memory-empty">还没有记忆。填写一条你希望保留的偏好或面试反馈，并核对后保存。</p>
          <ul class="memory-list">
            <li v-for="item in items" :key="item.id" class="memory-item">
              <div class="memory-meta"><strong>{{ item.kind === 'preference' ? '求职偏好' : '面试反馈' }}</strong><span>手动确认</span><time :datetime="item.confirmedAt">{{ formatDate(item.confirmedAt) }}</time></div>
              <p class="memory-content">{{ item.content }}</p>
              <button class="button-secondary danger-text" type="button" :disabled="busy" @click="remove(item.id)">{{ removingId === item.id ? '正在删除…' : '删除记忆' }}</button>
            </li>
          </ul>
          <div v-if="pendingDeletions.length" class="memory-pending" role="status">
            <strong>任务副本仍在清理</strong>
            <p>{{ pendingDeletions.length }} 条记忆的正文已删除。相关旧会话不能恢复，请新建任务继续准备。</p>
            <p>点击“刷新记忆状态”查看清理进度。</p>
          </div>
        </div>
      </div>
      <p v-if="error" class="error-note" role="alert">{{ error }}</p>
      <p v-if="notice" class="memory-notice" role="status">{{ notice }}</p>
      <p class="memory-deletion-note">删除已保存记忆及供任务继续使用的副本。已生成的简历、投递版本和原始面试记录仍保留。</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { deleteMemory, fetchMemories, saveMemory } from '../api/memories'
import { useAuthStore } from '../stores/auth'
import type { BusinessMemory, MemoryKind, PendingMemoryDeletion } from '../types/memory'

const auth = useAuthStore()
const items = ref<BusinessMemory[]>([]), pendingDeletions = ref<PendingMemoryDeletion[]>([])
const kind = ref<MemoryKind>('preference'), content = ref(''), confirmed = ref(false)
const loading = ref(false), saving = ref(false), removingId = ref(''), error = ref(''), notice = ref('')
const busy = computed(() => saving.value || Boolean(removingId.value))
let account = 0, listRequest = 0

function resetForm() { kind.value = 'preference'; content.value = ''; confirmed.value = false }
function errorMessage(cause: unknown) {
  if (cause instanceof Error && cause.message === 'Network Error') return '网络连接中断，请检查连接后重试。未保存的输入已保留。'
  return cause instanceof Error ? cause.message : '操作失败，请检查连接后重试。'
}
function formatDate(value: string) { return new Date(value).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' }) }

async function loadMemories() {
  if (!auth.token || busy.value) return
  const scope = account, request = ++listRequest
  loading.value = true; error.value = ''
  try {
    const result = await fetchMemories()
    if (scope !== account || request !== listRequest) return
    items.value = result.items; pendingDeletions.value = result.pendingDeletions
  } catch (cause) {
    if (scope === account && request === listRequest) error.value = errorMessage(cause)
  } finally {
    if (scope === account && request === listRequest) loading.value = false
  }
}

async function save() {
  if (!auth.token || loading.value || busy.value || !confirmed.value || !content.value.trim()) return
  const scope = account
  saving.value = true; error.value = ''; notice.value = ''
  listRequest++; loading.value = false
  try {
    const item = await saveMemory({ kind: kind.value, content: content.value.trim(), confirmed: true })
    if (scope !== account) return
    items.value = [item, ...items.value]; resetForm(); notice.value = '记忆已保存，下次新任务会使用。'
  } catch (cause) {
    if (scope === account) error.value = errorMessage(cause)
  } finally {
    if (scope === account) saving.value = false
  }
}

async function remove(id: string) {
  if (!auth.token || busy.value) return
  const scope = account
  removingId.value = id; error.value = ''; notice.value = ''
  // A list started before deletion must not bring the removed content back.
  listRequest++; loading.value = false
  try {
    const result = await deleteMemory(id)
    if (scope !== account) return
    items.value = items.value.filter(item => item.id !== id)
    pendingDeletions.value = pendingDeletions.value.filter(item => item.memoryId !== id)
    if (result.cleanupStatus === 'pending') {
      pendingDeletions.value.push({ memoryId: id, cleanupStatus: 'pending', affectedRunIds: result.affectedRunIds })
    } else {
      notice.value = result.newSessionRequired ? '已删除保存的记忆及任务副本。相关旧会话不能恢复，请新建任务继续准备。' : '已删除保存的记忆及任务副本。'
    }
  } catch (cause) {
    if (scope === account) error.value = errorMessage(cause)
  } finally {
    if (scope === account) removingId.value = ''
  }
}

watch(() => auth.token, () => {
  account++; listRequest++; items.value = []; pendingDeletions.value = []; resetForm()
  error.value = ''; notice.value = ''; loading.value = false; saving.value = false; removingId.value = ''
  if (auth.token) void loadMemories()
}, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { account++; listRequest++ })
</script>

<style scoped>
.business-memory { overflow-wrap: anywhere; }
.business-memory .section-head { flex-wrap: wrap; gap: 16px; }
.memory-workspace { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 32px; }
.memory-form,.memory-form > label { display: grid; gap: 8px; }
.memory-form { align-content: start; gap: 16px; }
.memory-form select,.memory-form textarea { width: 100%; min-width: 0; }
.memory-form textarea { resize: vertical; min-height: 120px; }
.memory-form .memory-confirm { display: flex; align-items: flex-start; gap: 10px; line-height: 1.6; }
.memory-confirm input { flex: 0 0 20px; margin-top: 3px; }
.memory-actions,.memory-meta,.memory-list-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.memory-list-head { justify-content: space-between; margin-bottom: 16px; }
.memory-list-head h3 { margin: 0; font-size: 16px; }
.memory-list-head > span,.memory-meta span,.memory-meta time,.muted-note,.memory-hint,.memory-deletion-note { color: var(--color-text-secondary); font-size: 14px; line-height: 1.7; }
.memory-hint { margin: -4px 0 0; }
.memory-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 16px; }
.memory-item { background: var(--surface-panel-muted); border: 1px solid var(--color-border); border-radius: var(--radius-sm); padding: 18px; }
.memory-meta strong { font-size: 14px; }
.memory-meta time { margin-left: auto; }
.memory-content { white-space: pre-wrap; margin: 12px 0 16px; line-height: 1.8; }
.memory-empty { margin: 0; padding: 24px; border: 1px dashed var(--color-border); border-radius: var(--radius-sm); color: var(--color-text-secondary); line-height: 1.8; }
.memory-pending { margin-top: 16px; padding: 16px 18px; border-left: 3px solid var(--color-warning); background: var(--surface-panel-muted); border-radius: var(--radius-sm); line-height: 1.7; }
.memory-pending p { margin: 8px 0 0; }
.memory-notice { color: var(--color-success); line-height: 1.7; }
.memory-deletion-note { border-top: 1px solid var(--color-border); padding-top: 20px; margin: 24px 0 0; }
@media (max-width: 900px) { .memory-workspace { grid-template-columns: 1fr; gap: 24px; } }
</style>

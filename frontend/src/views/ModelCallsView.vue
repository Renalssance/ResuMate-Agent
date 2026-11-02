<template>
  <div class="calls-page">
    <header class="calls-toolbar">
      <div><h2>模型调用</h2><p>查看当前账号每次调用的输入、输出与配置。仅记录功能启用后的调用。</p></div>
      <div class="toolbar-actions"><label><input v-model="autoRefresh" type="checkbox" />自动刷新 · 3 秒</label><button class="button-secondary" :disabled="loading" @click="load">刷新</button></div>
    </header>
    <p v-if="error" role="alert" class="error-note">{{ error }}</p>
    <section class="calls-table-wrap" aria-label="模型调用列表">
      <table>
        <thead><tr><th>时间 / 任务</th><th>模型</th><th>状态</th><th>耗时</th><th>输入 / 输出 Token</th><th></th></tr></thead>
        <tbody>
          <tr v-for="call in calls" :key="call.id" :class="{ selected: selectedId === call.id }">
            <td>{{ date(call.called_at) }}<small>{{ call.task }} · 第 {{ call.attempt }} 次尝试</small></td>
            <td>{{ call.model }}</td><td><span :class="['status', call.status]">{{ status(call.status) }}</span></td>
            <td>{{ (call.elapsed_ms / 1000).toFixed(1) }} 秒</td>
            <td>{{ tokens(call.usage?.prompt_tokens) }} / {{ tokens(call.usage?.completion_tokens) }}</td>
            <td><button class="button-secondary" :aria-label="`查看调用 ${call.id}`" @click="select(call.id)">查看</button></td>
          </tr>
        </tbody>
      </table>
      <p v-if="!calls.length" class="empty-state">{{ loading ? '加载中…' : '暂无调用记录。发起一次对话、解析或连接测试后可在这里查看。' }}</p>
    </section>
    <footer class="pagination"><span>共 {{ total }} 次调用</span><button class="button-secondary" :disabled="offset === 0 || loading" @click="page(-20)">上一页</button><button class="button-secondary" :disabled="offset + 20 >= total || loading" @click="page(20)">下一页</button></footer>
    <section v-if="selectedId" class="call-detail" aria-label="调用详情">
      <header><h3>调用 #{{ selectedId }}</h3><button class="button-secondary" @click="selectedId = null; detail = null">收起</button></header>
      <p v-if="detailError" role="alert">{{ detailError }}</p>
      <p v-if="!detail && !detailError">加载详情…</p>
      <template v-if="detail">
        <p class="endpoint">{{ detail.base_url }}</p>
        <p v-if="detail.error" class="error-note">{{ detail.error }}</p>
        <div class="detail-tabs" role="tablist" aria-label="调用内容">
          <button v-for="tab in tabs" :key="tab.key" role="tab" :aria-selected="activeTab === tab.key" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">{{ tab.label }}</button>
        </div>
        <p v-if="activeTab === 'usage' && !detail.usage" class="note">接口未返回 Token 用量，无法统计；不代表消耗为 0。</p>
        <p v-if="activeTab === 'config'" class="note">显示本次请求实际指定的参数；未指定的参数由服务端决定。</p>
        <p v-if="detail.status === 'running'" class="note">调用尚未结束，已接收的输出会随自动刷新更新。若服务被强制关闭，记录可能停留在此状态。</p>
        <pre role="tabpanel" tabindex="0">{{ panelText }}</pre>
      </template>
    </section>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { fetchModelCalls, fetchModelCall, type ModelCall, type ModelCallDetail } from '../api/llmCalls'
const calls = ref<ModelCall[]>([]), detail = ref<ModelCallDetail | null>(null)
const total = ref(0), offset = ref(0), selectedId = ref<number | null>(null)
const loading = ref(false), autoRefresh = ref(true), error = ref(''), detailError = ref('')
const activeTab = ref('output')
const tabs = [{ key: 'config', label: '模型配置' }, { key: 'input', label: 'Prompt 输入' }, { key: 'output', label: '输出内容' }, { key: 'usage', label: 'Token 用量' }]
const panelText = computed(() => {
  if (!detail.value) return ''
  const { messages, ...config } = detail.value.request
  const value = activeTab.value === 'input' ? messages : activeTab.value === 'config' ? config : activeTab.value === 'usage' ? detail.value.usage : detail.value.output
  return value == null ? '尚无内容' : JSON.stringify(value, null, 2)
})
function status(value: string) { return ({ running: '进行中', completed: '已完成', failed: '失败', truncated: '长度截断' } as Record<string, string>)[value] || value }
function tokens(value: unknown) { return typeof value === 'number' ? value.toLocaleString() : '—' }
function date(value: string) { return new Date(value).toLocaleString('zh-CN', { hour12: false }) }
async function select(id: number) {
  if (selectedId.value !== id) detail.value = null
  selectedId.value = id; detailError.value = ''
  try { const result = await fetchModelCall(id); if (selectedId.value === id) detail.value = result }
  catch (e) { if (selectedId.value === id) detailError.value = e instanceof Error ? e.message : '详情加载失败' }
}
async function load() {
  if (loading.value) return
  loading.value = true; error.value = ''
  try {
    const result = await fetchModelCalls(offset.value); calls.value = result.items; total.value = result.total
    if (selectedId.value) await select(selectedId.value)
  } catch (e) { error.value = e instanceof Error ? e.message : '加载失败' }
  finally { loading.value = false }
}
function page(delta: number) { offset.value += delta; void load() }
let timer: ReturnType<typeof setInterval>
onMounted(() => { void load(); timer = setInterval(() => { if (autoRefresh.value && !document.hidden) void load() }, 3000) })
onBeforeUnmount(() => clearInterval(timer))
</script>
<style scoped>
.calls-page { display: grid; gap: 20px; min-width: 0; }
.calls-toolbar, .call-detail header, .pagination, .toolbar-actions { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.calls-toolbar, .call-detail header { justify-content: space-between; }
h2, h3 { margin: 0; } p { line-height: 1.6; } .calls-toolbar p, .note, .endpoint { opacity: .7; font-size: 13px; }
.calls-table-wrap, .call-detail { background: var(--surface, #fffaf4); border: 1px solid var(--border, #e7ddd2); border-radius: 16px; overflow: auto; }
table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; white-space: nowrap; }
th, td { padding: 16px; border-bottom: 1px solid var(--border, #e7ddd2); } th { opacity: .65; font-weight: 500; } td small { display: block; margin-top: 6px; opacity: .6; }
tr.selected { background: #eee4d6; } .status { padding: 4px 8px; border-radius: 6px; background: #e8ece4; } .status.failed, .status.truncated { background: #f7e4d8; color: #9b422a; } .status.running { background: #e0ecf3; }
.pagination { justify-content: flex-end; font-size: 13px; } .pagination span { margin-right: auto; }.call-detail { padding: 24px; min-width: 0; }.endpoint { overflow-wrap: anywhere; }
.detail-tabs { display: flex; gap: 6px; flex-wrap: wrap; margin: 20px 0 12px; }.detail-tabs button { background: transparent; border: 0; padding: 9px 14px; border-radius: 8px; color: inherit; cursor: pointer; }.detail-tabs .active { background: #e9ddcd; font-weight: 600; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 600px; overflow: auto; background: #f4efe8; padding: 20px; border-radius: 10px; font: 13px/1.7 ui-monospace, monospace; }.empty-state { padding: 30px; text-align: center; }
@media (max-width: 700px) { .call-detail { padding: 14px; } pre { padding: 12px; } }
</style>

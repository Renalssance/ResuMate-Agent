<template>
  <div class="page-stack settings-page settings-dashboard">
    <div class="settings-models">
      <section class="model-card" aria-labelledby="llm-heading">
        <form class="model-inline-form" @submit.prevent="saveSettings" @keydown.esc="cancelEditSettings">
          <header class="model-card-head">
            <h2 id="llm-heading"><Box class="app-icon" />LLM</h2>
            <div class="model-actions">
              <button type="button" class="model-test" :disabled="loading || saving || testing || !settings" @click="testConnection"><Play class="app-icon" />{{ testing ? '测试中' : '测试' }}</button>
              <button v-if="editingSettings" type="submit" class="model-edit model-save" :disabled="saving || testing"><Save class="app-icon" />{{ saving ? '保存中' : '保存' }}</button>
              <button v-else type="button" class="model-edit" :disabled="loading || !settings" @click="startEditSettings"><Pencil class="app-icon" />编辑</button>
            </div>
          </header>
          <input v-model.trim="form.model" class="model-name" aria-label="LLM 模型名称" :title="form.model" :readonly="!editingSettings" :disabled="saving" placeholder="配置模型名称" required />
          <div class="model-fields model-credentials">
            <label class="model-field"><span>API Key</span><input id="settings-api-key" v-model.trim="form.api_key" :title="form.api_key" :readonly="!editingSettings" :disabled="saving" autocomplete="off" placeholder="未配置" /></label>
            <label class="model-field"><span>Base URL</span><input v-model.trim="form.base_url" :title="form.base_url" :readonly="!editingSettings" :disabled="saving" placeholder="未配置" required /></label>
          </div>
          <div class="model-fields model-limits">
            <label class="model-field"><span>输出上限</span><input v-model.number="form.max_tokens" :type="editingSettings ? 'number' : 'text'" min="1" :readonly="!editingSettings" :disabled="saving" required /></label>
            <label class="model-field"><span>上下文容量</span><input id="settings-context-window" v-model.number="form.context_window_tokens" :type="editingSettings ? 'number' : 'text'" min="1" :readonly="!editingSettings" :disabled="saving" placeholder="未配置" /></label>
            <label class="model-field"><span>超时</span><input v-model.number="form.request_timeout_seconds" :type="editingSettings ? 'number' : 'text'" min="1" :readonly="!editingSettings" :disabled="saving" required /><span class="field-unit">秒</span></label>
          </div>
          <div class="model-feedback">
            <span v-if="error" role="alert">{{ error }}</span>
            <span v-else-if="message" role="status">{{ message }}</span>
            <span v-else-if="loading" role="status">加载中…</span>
            <button v-if="error && !editingSettings" type="button" @click="loadAll">重试</button>
          </div>
        </form>
      </section>
      <EmbeddingSettingsCard v-if="auth.isAuthenticated" :key="auth.token" />
    </div>

    <section class="settings-usage">
      <div class="usage-toolbar">
        <button class="button-secondary" type="button" :disabled="loading || saving || editingSettings || !auth.isAuthenticated" @click="loadAll">
          <RefreshCw class="app-icon" aria-hidden="true" />
          <span>刷新</span>
        </button>
      </div>

      <p v-if="loading" class="loading-state" role="status">{{ usage ? '正在刷新统计…' : '正在加载统计…' }}</p>
      <p v-if="!usage && error" class="error-note" role="alert">统计加载失败，请重新加载。</p>
      <template v-if="usage">
      <div class="settings-overview-grid">
        <article class="dashboard-metric">
          <span><Activity class="app-icon" />调用次数</span>
          <strong>{{ usage?.total_calls ?? 0 }}</strong>
          <small>成功 {{ usage?.successful_calls ?? 0 }} / 失败 {{ usage?.failed_calls ?? 0 }}</small>
        </article>
        <article class="dashboard-metric">
          <span><Coins class="app-icon" />总 Token</span>
          <strong>{{ formatNumber(usage?.total_tokens ?? 0) }}</strong>
          <small>输入 {{ formatNumber(usage?.prompt_tokens ?? 0) }} / 输出 {{ formatNumber(usage?.completion_tokens ?? 0) }}</small>
        </article>
        <article class="dashboard-metric">
          <span><ShieldCheck class="app-icon" />成功率</span>
          <strong>{{ usage.success_rate }}<em>%</em></strong>
          <div class="success-ring" :style="{ '--success': `${usage.success_rate}%` }" aria-hidden="true"></div>
          <small>最近调用 {{ usage.last_called_at ? formatDateTime(usage.last_called_at) : '—' }}</small>
        </article>
      </div>

      <div class="settings-dashboard-grid">
        <article class="settings-chart-panel">
          <div class="section-head compact">
            <div>
              <h3><ChartNoAxesColumnIncreasing class="app-icon" />每日消耗</h3>
            </div>
          </div>
          <div v-if="dailyBars.length" class="usage-day-strip">
            <div v-for="item in dailyBars" :key="item.date" class="usage-day">
              <div class="usage-day-bars">
                <span class="token-bar" :style="{ height: `${item.tokenPercent}%` }"></span>
              </div>
              <strong>{{ item.label }}</strong>
              <small>{{ formatNumber(item.total_tokens) }}</small>
            </div>
          </div>
          <EmptyState v-else title="暂无调用" description="模型调用完成后，这里会出现每日消耗。" />
        </article>

        <article class="settings-chart-panel task-distribution">
          <div class="section-head compact">
            <div>
              <h3><ChartPie class="app-icon" />任务分布</h3>
            </div>
          </div>
          <div v-if="taskBars.length" class="usage-task-list">
            <div v-for="item in taskBars" :key="item.task" class="usage-task-row">
              <div>
                <strong>{{ taskName(item.task) }}</strong>
                <small>{{ item.calls }} 次 / {{ formatNumber(item.total_tokens) }} token</small>
              </div>
              <span><i :style="{ width: `${Math.max(item.percent, 3)}%` }"></i></span>
            </div>
          </div>
          <EmptyState v-else title="暂无任务" description="聊天、文档解析、匹配或试题生成后会自动统计。" />
        </article>
      </div>

      <div class="settings-recent-panel">
        <div class="section-head compact">
          <div>
            <h3><Clock3 class="app-icon" />最近调用</h3>
          </div>
        </div>
        <div v-if="usage?.recent_calls.length" class="table-wrap">
          <table class="data-table settings-usage-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>任务</th>
                <th>模型</th>
                <th>Token</th>
                <th>耗时</th>
                <th>结果</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in usage.recent_calls" :key="item.id">
                <td>{{ formatDateTime(item.called_at) }}</td>
                <td>{{ taskName(item.task) }}</td>
                <td>{{ item.model || '-' }}</td>
                <td>{{ formatNumber(item.total_tokens) }}</td>
                <td>{{ item.elapsed_ms }} ms</td>
                <td>
                  <span :class="['status-tag', item.success ? 'success' : 'danger']">
                    {{ item.success ? '成功' : item.error_type || '失败' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <EmptyState v-else title="暂无调用记录" description="调用记录会按当前账号保存。" />
      </div>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
import { Activity, Box, ChartNoAxesColumnIncreasing, ChartPie, Clock3, Coins, Pencil, Play, RefreshCw, Save, ShieldCheck } from '@lucide/vue'
import '../styles/settingsDashboard.css'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { fetchLlmSettingsApi, fetchLlmUsageApi, saveLlmSettingsApi, testLlmSettingsApi } from '../api/settings'
import EmbeddingSettingsCard from '../components/EmbeddingSettingsCard.vue'
import EmptyState from '../components/EmptyState.vue'
import { useAuthStore } from '../stores/auth'
import type { LlmSettingsResponse, LlmUsageDashboard } from '../types/settings'
import { buildUsageDailyBars, buildUsageTaskBars } from '../utils/usageChart'

const auth = useAuthStore()
const router = useRouter()
const settings = ref<LlmSettingsResponse | null>(null)
const usage = ref<LlmUsageDashboard | null>(null)
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const editingSettings = ref(false)
const error = ref('')
const message = ref('')
const form = reactive({
  api_key: '',
  base_url: '',
  model: '',
  max_tokens: 8192,
  context_window_tokens: '' as number | '',
  request_timeout_seconds: 300,
})

const needsConfiguration = computed(() => Boolean(settings.value && (
  !settings.value.has_api_key || !settings.value.base_url || !settings.value.model
)))

const dailyBars = computed(() => buildUsageDailyBars(usage.value?.daily ?? []))
const taskBars = computed(() => buildUsageTaskBars(usage.value?.by_task ?? []))
async function loadAll() {
  if (!auth.isAuthenticated) return
  loading.value = true
  error.value = ''
  try {
    const nextSettings = await fetchLlmSettingsApi()
    settings.value = nextSettings
    if (!editingSettings.value) Object.assign(form, {
      api_key: nextSettings.api_key,
      base_url: nextSettings.base_url,
      model: nextSettings.model,
      max_tokens: nextSettings.max_tokens,
      context_window_tokens: nextSettings.context_window_tokens ?? '',
      request_timeout_seconds: nextSettings.request_timeout_seconds,
    })
    if (needsConfiguration.value) editingSettings.value = true
    usage.value = await fetchLlmUsageApi()
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    if (isExpiredTokenMessage(message)) {
      logout()
      return
    }
    error.value = settings.value ? '刷新失败，已显示的配置可能不是最新。请检查服务连接后重试。' : '配置加载失败，请检查服务连接后重试。'
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  if (saving.value) return
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    settings.value = await saveLlmSettingsApi({
      api_key: form.api_key,
      base_url: form.base_url,
      model: form.model,
      max_tokens: form.max_tokens,
      context_window_tokens: form.context_window_tokens === '' ? null : form.context_window_tokens,
      request_timeout_seconds: form.request_timeout_seconds,
    })
    form.api_key = settings.value.api_key
    editingSettings.value = false
    message.value = '设置已保存'
    window.dispatchEvent(new CustomEvent('llm-settings-updated', { detail: { model: settings.value.model } }))
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    saving.value = false
  }
}

function startEditSettings() {
  message.value = ''
  error.value = ''
  editingSettings.value = true
}

function cancelEditSettings() {
  editingSettings.value = false
  message.value = ''
  error.value = ''
  if (!settings.value) return
  Object.assign(form, {
    api_key: settings.value.api_key,
    base_url: settings.value.base_url,
    model: settings.value.model,
    max_tokens: settings.value.max_tokens,
    context_window_tokens: settings.value.context_window_tokens ?? '',
    request_timeout_seconds: settings.value.request_timeout_seconds,
  })
}

function logout() {
  auth.logout()
  settings.value = null
  usage.value = null
  editingSettings.value = false
  void router.push('/')
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value)
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function taskName(task: string) {
  return ({
    chat: '聊天',
    'agent.chat_stream': '聊天',
    connection_test: '连接测试',
    'document.classify': '文档分类',
    'document.parse_resume': '简历解析',
    'document.parse_jd': '职位解析',
    evaluate_match: '匹配评估',
    match_analysis: '匹配分析',
    plan_question_blueprint: '试题规划',
    generate_question_batch: '试题生成',
    generate_questions: '试题生成',
    generate_ambiguity_followups: '追问生成',
    'followup.analyze_answer': '回答分析',
    tailoring: '简历定制',
    unknown: '未分类任务',
  } as Record<string, string>)[task] ?? '其他任务'
}

async function testConnection() {
  testing.value = true
  error.value = ''; message.value = ''
  try {
    await testLlmSettingsApi()
    message.value = '连接成功'
    usage.value = await fetchLlmUsageApi()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '连接测试失败'
  } finally { testing.value = false }
}

function isExpiredTokenMessage(value: string) {
  return value.includes('无效或过期')
}

watch(() => auth.token, loadAll)
onMounted(loadAll)
</script>

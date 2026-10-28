<template>
  <div class="page-stack settings-page">
    <section class="card settings-section-card settings-config-card">
      <div class="section-head compact">
        <div>
          <h2>模型参数</h2>
        </div>
        <div class="settings-head-actions">
          <button v-if="!editingSettings" class="button-primary" type="button" :disabled="loading || !auth.isAuthenticated || !settings" @click="startEditSettings">
            <Pencil class="app-icon" aria-hidden="true" />
            <span>{{ needsConfiguration ? '配置模型' : '编辑' }}</span>
          </button>
        </div>
      </div>

      <p v-if="needsConfiguration" class="settings-message">尚未完成模型配置。请选择厂商地址，并填写自己的 API Key 和模型名称后保存。</p>

      <div v-if="!editingSettings" class="settings-parameter-grid" :aria-busy="loading">
        <article v-for="item in parameterItems" :key="item.label" class="settings-parameter" :class="{ 'settings-parameter-wide': item.label === 'Base URL' }">
          <span
            :class="['settings-parameter-status', { missing: settings && !item.configured }]"
            role="img"
            :aria-label="!settings ? (loading ? '加载中' : error ? '加载失败' : '待加载') : item.configured ? '已配置' : '未配置'"
          >
            <span v-if="!settings" aria-hidden="true">—</span>
            <Check v-else-if="item.configured" class="app-icon" aria-hidden="true" />
            <X v-else class="app-icon" aria-hidden="true" />
          </span>
          <span class="settings-parameter-label">{{ item.label }}</span>
          <strong :class="{ 'is-secret': item.secret }" :title="settings && item.configured && !item.secret ? item.value : undefined">{{ !settings ? '—' : item.configured ? item.value : '尚未设置' }}</strong>
        </article>
      </div>

      <form v-else class="settings-config-form" @submit.prevent="saveSettings">
        <div class="settings-provider-presets">
          <span>快速填入厂商 Base URL</span>
          <div class="settings-provider-buttons">
            <button v-for="provider in modelProviders" :key="provider.name" class="button-secondary" type="button" @click="form.base_url = provider.baseUrl">{{ provider.name }}</button>
          </div>
          <small>仅填入地址，不会自动保存。请填写该厂商支持的模型名称；使用其他地区或代理服务时可手动修改地址。Claude 请使用工作区 API Key。</small>
        </div>
        <div class="settings-key-field settings-field-half">
          <div class="settings-key-heading">
            <label for="settings-api-key"><span>API Key</span></label>
            <label class="settings-checkbox">
              <input v-model="form.clear_api_key" type="checkbox" :disabled="!settings?.has_api_key" />
              <span>清空已保存 Key</span>
            </label>
          </div>
          <input id="settings-api-key" v-model.trim="form.api_key" type="password" autocomplete="off" :placeholder="settings?.has_api_key ? '已配置，留空保留原密钥' : '请输入 API Key'" :disabled="form.clear_api_key" />
        </div>
        <label class="settings-field-half">
          <span>API 地址 · Base URL</span>
          <input v-model.trim="form.base_url" placeholder="https://api.openai.com/v1" />
        </label>
        <label>
          <span>模型名称 · Model</span>
          <input v-model.trim="form.model" placeholder="请输入厂商提供的模型名称" />
        </label>
        <label>
          <span>输出 Token 上限</span>
          <input v-model.number="form.max_tokens" min="1" type="number" />
        </label>
        <label>
          <span>请求超时（秒）</span>
          <input v-model.number="form.request_timeout_seconds" min="1" type="number" />
        </label>
        <div class="form-actions">
          <button class="button-secondary" type="button" :disabled="saving" @click="cancelEditSettings">
            <X class="app-icon" aria-hidden="true" />
            <span>取消</span>
          </button>
          <button class="button-primary" type="submit" :disabled="saving || !auth.isAuthenticated">
            <Save class="app-icon" aria-hidden="true" />
            <span>{{ saving ? '保存中...' : '保存' }}</span>
          </button>
        </div>
      </form>
      <p v-if="message" class="settings-message">{{ message }}</p>
      <div v-if="error" class="settings-load-error" role="alert">
        <p class="settings-inline-error">{{ error }}</p>
        <button v-if="!editingSettings" class="button-secondary" type="button" :disabled="loading" @click="loadAll">重新加载</button>
      </div>
      <p v-if="!auth.isAuthenticated" class="settings-inline-error">请从首页登录后查看模型配置。</p>
    </section>

    <section class="card settings-section-card settings-dashboard-card">
      <div class="section-head compact">
        <div>
          <h2>Token 看板</h2>
          <p>统计当前账号的调用次数、token 消耗和调用时间。</p>
        </div>
        <button class="button-secondary" type="button" :disabled="loading || saving || editingSettings || !auth.isAuthenticated" @click="loadAll">
          <RefreshCw class="app-icon" aria-hidden="true" />
          <span>刷新</span>
        </button>
      </div>

      <p v-if="loading" class="loading-state" role="status">{{ usage ? '正在刷新统计…' : '正在加载统计…' }}</p>
      <p v-if="!usage && error" class="error-note" role="alert">统计加载失败，请重新加载。</p>
      <template v-if="usage">
      <div class="settings-overview-grid">
        <article class="metric-card settings-metric">
          <span>调用次数</span>
          <strong>{{ usage?.total_calls ?? 0 }}</strong>
          <small>成功 {{ usage?.successful_calls ?? 0 }} / 失败 {{ usage?.failed_calls ?? 0 }}</small>
        </article>
        <article class="metric-card settings-metric">
          <span>消耗 Token</span>
          <strong>{{ formatNumber(usage?.total_tokens ?? 0) }}</strong>
          <small>输入 {{ formatNumber(usage?.prompt_tokens ?? 0) }} / 输出 {{ formatNumber(usage?.completion_tokens ?? 0) }}</small>
        </article>
        <article class="metric-card settings-metric">
          <span>最近调用</span>
          <strong>{{ usage?.last_called_at ? formatShortDate(usage.last_called_at) : '-' }}</strong>
          <small>成功率 {{ usage?.success_rate ?? 0 }}%</small>
        </article>
      </div>

      <div class="settings-dashboard-grid">
        <article class="settings-chart-panel">
          <div class="section-head compact">
            <div>
              <h3>每日 Token</h3>
              <p>按调用日期聚合。</p>
            </div>
          </div>
          <div v-if="dailyBars.length" class="usage-day-strip">
            <div v-for="item in dailyBars" :key="item.date" class="usage-day">
              <div class="usage-day-bars">
                <span class="token-bar" :style="{ height: `${Math.max(item.tokenPercent, 4)}%` }"></span>
                <span class="call-bar" :style="{ height: `${Math.max(item.callPercent, 4)}%` }"></span>
              </div>
              <strong>{{ item.label }}</strong>
              <small>{{ formatNumber(item.total_tokens) }}</small>
            </div>
          </div>
          <EmptyState v-else title="暂无调用" description="模型调用完成后，这里会出现每日消耗。" />
        </article>

        <article class="settings-chart-panel">
          <div class="section-head compact">
            <div>
              <h3>任务分布</h3>
              <p>按任务类型聚合。</p>
            </div>
          </div>
          <div v-if="taskBars.length" class="usage-task-list">
            <div v-for="item in taskBars" :key="item.task" class="usage-task-row">
              <div>
                <strong>{{ item.task }}</strong>
                <small>{{ item.calls }} 次 / {{ formatNumber(item.total_tokens) }} token</small>
              </div>
              <span><i :style="{ width: `${Math.max(item.percent, 3)}%` }"></i></span>
            </div>
          </div>
          <EmptyState v-else title="暂无任务" description="完成文档解析、匹配或试题生成后会自动统计。" />
        </article>
      </div>

      <div class="settings-recent-panel">
        <div class="section-head compact">
          <div>
            <h3>最近调用</h3>
            <p>按时间倒序排列。</p>
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
                <td>{{ item.task }}</td>
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
import { Check, Pencil, RefreshCw, Save, X } from '@lucide/vue'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { fetchLlmSettingsApi, fetchLlmUsageApi, saveLlmSettingsApi } from '../api/settings'
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
const editingSettings = ref(false)
const error = ref('')
const message = ref('')
const form = reactive({
  api_key: '',
  clear_api_key: false,
  base_url: '',
  model: '',
  max_tokens: 8192,
  request_timeout_seconds: 300,
})

const modelProviders = [
  { name: 'OpenAI / ChatGPT', baseUrl: 'https://api.openai.com/v1' },
  { name: 'Claude', baseUrl: 'https://api.anthropic.com/v1' },
  { name: 'DeepSeek', baseUrl: 'https://api.deepseek.com' },
  { name: 'Qwen / 通义千问', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { name: 'Kimi', baseUrl: 'https://api.moonshot.cn/v1' },
]
const needsConfiguration = computed(() => Boolean(settings.value && (
  !settings.value.has_api_key || !settings.value.base_url || !settings.value.model
)))

const dailyBars = computed(() => buildUsageDailyBars(usage.value?.daily ?? []))
const taskBars = computed(() => buildUsageTaskBars(usage.value?.by_task ?? []))
const parameterItems = computed(() => [
  { label: '模型', configured: Boolean(settings.value?.model?.trim()), value: settings.value?.model, secret: false },
  { label: 'API Key', configured: Boolean(settings.value?.has_api_key), value: '••••••••', secret: true },
  { label: 'Token 上限', configured: Number(settings.value?.max_tokens) > 0, value: settings.value?.max_tokens?.toLocaleString(), secret: false },
  { label: '超时', configured: Number(settings.value?.request_timeout_seconds) > 0, value: `${settings.value?.request_timeout_seconds} 秒`, secret: false },
  { label: 'Base URL', configured: Boolean(settings.value?.base_url?.trim()), value: settings.value?.base_url, secret: false },
])

async function loadAll() {
  if (!auth.isAuthenticated) return
  loading.value = true
  error.value = ''
  try {
    const nextSettings = await fetchLlmSettingsApi()
    settings.value = nextSettings
    if (!editingSettings.value) Object.assign(form, {
      api_key: '',
      clear_api_key: false,
      base_url: nextSettings.base_url,
      model: nextSettings.model,
      max_tokens: nextSettings.max_tokens,
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
      clear_api_key: form.clear_api_key,
      base_url: form.base_url,
      model: form.model,
      max_tokens: form.max_tokens,
      request_timeout_seconds: form.request_timeout_seconds,
    })
    form.api_key = ''
    form.clear_api_key = false
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
    api_key: '',
    clear_api_key: false,
    base_url: settings.value.base_url,
    model: settings.value.model,
    max_tokens: settings.value.max_tokens,
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

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(value))
}

function isExpiredTokenMessage(value: string) {
  return value.includes('无效或过期')
}

watch(() => auth.token, loadAll)
onMounted(loadAll)
</script>

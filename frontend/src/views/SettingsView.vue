<template>
  <div class="page-stack settings-page">
    <section class="card settings-section-card settings-account-card">
      <div class="section-head compact">
        <div>
          <h2>账号管理</h2>
        </div>
        <form v-if="!auth.isAuthenticated" class="settings-auth-form" @submit.prevent="submitAuth('login')">
          <div class="settings-auth-inputs">
            <input v-model.trim="credentials.username" autocomplete="username" placeholder="用户名" aria-label="用户名" />
            <input v-model="credentials.password" autocomplete="current-password" type="password" placeholder="密码" aria-label="密码" />
          </div>
          <div class="settings-auth-actions">
            <button class="button-primary" type="submit" :disabled="auth.loading">登录</button>
            <button class="button-secondary glass-action" type="button" :disabled="auth.loading" @click="submitAuth('register')">
              注册
            </button>
          </div>
        </form>
        <div v-else class="settings-account-state">
          <span>{{ auth.username }}</span>
          <small>{{ auth.role || 'user' }}</small>
          <button class="button-secondary glass-action" type="button" @click="logout">
            <span class="icon-glyph close" aria-hidden="true"></span>
            <span>退出账号</span>
          </button>
        </div>
      </div>

      <p v-if="auth.error && !isExpiredTokenMessage(auth.error)" class="settings-inline-error">{{ auth.error }}</p>
    </section>

    <section class="card settings-section-card settings-config-card">
      <div class="section-head compact">
        <div>
          <h2>模型参数</h2>
        </div>
        <div class="settings-head-actions">
          <button v-if="!editingSettings" class="button-secondary glass-action" type="button" :disabled="!auth.isAuthenticated" @click="startEditSettings">
            <span class="icon-glyph edit" aria-hidden="true"></span>
            <span>编辑</span>
          </button>
        </div>
      </div>

      <div v-if="!editingSettings" class="settings-model-read">
        <div class="settings-model-hero glass-surface-strong">
          <span>
            当前模型
            <small v-if="settingsIncomplete" class="settings-mini-warning">未配置</small>
          </span>
          <strong>{{ settings?.model || '未配置 model' }}</strong>
        </div>
      </div>

      <form v-else class="settings-config-form" @submit.prevent="saveSettings">
        <label class="span-two">
          <span>Model</span>
          <input v-model.trim="form.model" placeholder="gpt-4.1-mini" />
        </label>
        <div class="settings-form-pair span-two">
          <label class="span-two">
            <span>API Key</span>
            <input v-model.trim="form.api_key" type="password" autocomplete="off" placeholder="留空则保留原 Key" />
          </label>
          <label class="settings-checkbox">
            <input v-model="form.clear_api_key" type="checkbox" />
            <span>清空已保存 Key</span>
          </label>
        </div>
        <label class="span-two">
          <span>Base URL</span>
          <input v-model.trim="form.base_url" placeholder="https://api.openai.com/v1" />
        </label>
        <label>
          <span>Max tokens</span>
          <input v-model.number="form.max_tokens" min="1" type="number" />
        </label>
        <label>
          <span>Timeout 秒</span>
          <input v-model.number="form.request_timeout_seconds" min="1" type="number" />
        </label>
        <div class="settings-button-row span-two">
          <button class="button-primary" type="submit" :disabled="saving || !auth.isAuthenticated">
            <span class="icon-glyph save" aria-hidden="true"></span>
            <span>{{ saving ? '保存中...' : '保存' }}</span>
          </button>
          <button class="button-secondary glass-action" type="button" :disabled="saving" @click="cancelEditSettings">
            <span class="icon-glyph close" aria-hidden="true"></span>
            <span>取消</span>
          </button>
        </div>
      </form>
      <p v-if="message" class="settings-message">{{ message }}</p>
      <p v-if="error && editingSettings" class="settings-inline-error">{{ error }}</p>
    </section>

    <section class="card settings-section-card settings-dashboard-card">
      <div class="section-head compact">
        <div>
          <h2>Token 看板</h2>
          <p>统计当前账号的调用次数、token 消耗和调用时间。</p>
        </div>
        <button class="button-secondary glass-action" type="button" :disabled="loading || !auth.isAuthenticated" @click="loadAll">
          <span class="icon-glyph refresh" aria-hidden="true"></span>
          <span>刷新</span>
        </button>
      </div>

      <div class="settings-overview-grid">
        <article class="metric-card glass-surface settings-metric">
          <span>调用次数</span>
          <strong>{{ usage?.total_calls ?? 0 }}</strong>
          <small>成功 {{ usage?.successful_calls ?? 0 }} / 失败 {{ usage?.failed_calls ?? 0 }}</small>
        </article>
        <article class="metric-card glass-surface settings-metric">
          <span>消耗 Token</span>
          <strong>{{ formatNumber(usage?.total_tokens ?? 0) }}</strong>
          <small>输入 {{ formatNumber(usage?.prompt_tokens ?? 0) }} / 输出 {{ formatNumber(usage?.completion_tokens ?? 0) }}</small>
        </article>
        <article class="metric-card glass-surface settings-metric">
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
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { fetchLlmSettingsApi, fetchLlmUsageApi, saveLlmSettingsApi } from '../api/settings'
import EmptyState from '../components/EmptyState.vue'
import { useAuthStore } from '../stores/auth'
import type { LlmSettingsResponse, LlmUsageDashboard } from '../types/settings'
import { buildUsageDailyBars, buildUsageTaskBars } from '../utils/usageChart'

type AuthMode = 'login' | 'register'

const auth = useAuthStore()
const settings = ref<LlmSettingsResponse | null>(null)
const usage = ref<LlmUsageDashboard | null>(null)
const loading = ref(false)
const saving = ref(false)
const editingSettings = ref(false)
const error = ref('')
const message = ref('')
const credentials = reactive({ username: '', password: '' })
const form = reactive({
  api_key: '',
  clear_api_key: false,
  base_url: '',
  model: '',
  max_tokens: 8192,
  request_timeout_seconds: 300,
})

const dailyBars = computed(() => buildUsageDailyBars(usage.value?.daily ?? []))
const taskBars = computed(() => buildUsageTaskBars(usage.value?.by_task ?? []))
const settingsIncomplete = computed(
  () => !settings.value || !settings.value.model || !settings.value.base_url || !settings.value.has_api_key,
)

async function loadAll() {
  if (!auth.isAuthenticated) return
  loading.value = true
  error.value = ''
  try {
    const [nextSettings, nextUsage] = await Promise.all([fetchLlmSettingsApi(), fetchLlmUsageApi()])
    settings.value = nextSettings
    usage.value = nextUsage
    Object.assign(form, {
      api_key: '',
      clear_api_key: false,
      base_url: nextSettings.base_url,
      model: nextSettings.model,
      max_tokens: nextSettings.max_tokens,
      request_timeout_seconds: nextSettings.request_timeout_seconds,
    })
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    if (isExpiredTokenMessage(message)) {
      logout()
      return
    }
    error.value = message
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
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

async function submitAuth(mode: AuthMode) {
  try {
    await auth.submit(mode, credentials)
    credentials.password = ''
    await loadAll()
  } catch {
    credentials.password = ''
  }
}

function logout() {
  auth.logout()
  settings.value = null
  usage.value = null
  editingSettings.value = false
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

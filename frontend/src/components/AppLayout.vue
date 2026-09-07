<template>
  <div :class="['app-shell', isGlassTheme ? 'is-glass-theme' : 'is-simple-theme']">
    <div id="box" class="fluid-bg" aria-hidden="true"></div>

    <aside :class="['app-sidebar', { open: drawerOpen }]">
      <div class="brand">
        <div class="brand-mark">R</div>
        <div>
          <strong>ResuMate Agent</strong>
          <span>AI 招聘工作台</span>
        </div>
      </div>
      <nav class="nav-list">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          class="nav-item"
          :to="item.path"
          @click="drawerOpen = false"
        >
          <span :class="['nav-icon', item.icon]" aria-hidden="true"></span>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <AgentStatusPanel
        class="sidebar-agent-status"
        title="Agent 状态"
        :task-id="agentStatus.taskId.value"
        :current="agentStatus.current.value"
        :events="agentStatus.events.value"
      />
    </aside>

    <div v-if="drawerOpen" class="drawer-mask" @click="drawerOpen = false"></div>

    <main class="app-main">
      <header class="topbar">
        <button class="icon-button mobile-only" type="button" aria-label="打开导航" @click="drawerOpen = true">
          <span class="icon-glyph menu" aria-hidden="true"></span>
        </button>
        <div class="topbar-title">
          <h1>{{ route.meta.title }}</h1>
          <p>{{ route.meta.description }}</p>
        </div>

        <div class="topbar-actions">
          <span
            v-if="llmModel !== null"
            :class="['llm-model-status', { 'is-missing': !llmModel }]"
          >
            {{ llmModel || '未配置LLM_MODEL' }}
          </span>
          <label class="appearance-switch">
            <span>玻璃效果</span>
            <input
              type="checkbox"
              role="switch"
              :checked="isGlassTheme"
              :aria-checked="isGlassTheme"
              @change="toggleAppearance"
            >
            <i aria-hidden="true"></i>
          </label>
        </div>
      </header>
      <div class="content-wrap">
        <RouterView />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { AestheticFluidBg } from 'color4bg'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { fetchLlmSettingsApi } from '../api/settings'
import { useAgentStatus } from '../composables/useAgentStatus'
import { useAuthStore } from '../stores/auth'
import AgentStatusPanel from './AgentStatusPanel.vue'

const route = useRoute()
const auth = useAuthStore()
const agentStatus = useAgentStatus()
const drawerOpen = ref(false)
const llmModel = ref<string | null>(null)
const APPEARANCE_STORAGE_KEY = 'resumate:appearance-style'
const isGlassTheme = ref(localStorage.getItem(APPEARANCE_STORAGE_KEY) === 'glass')
const fluidBackgroundColors = ["#1D4600", "#4F9900", "#82C23A", "#D7E356", "#A5C940", "#1D4600"]
let colorbg: AestheticFluidBg | null = null

const navItems = [
  { path: '/documents', label: '文档管理', icon: 'documents' },
  { path: '/matching', label: '岗位匹配', icon: 'matching' },
  { path: '/profile-fields', label: '结构资料', icon: 'profile' },
  { path: '/questions', label: '试题生成', icon: 'questions' },
  { path: '/applications', label: '投递记录', icon: 'applications' },
  { path: '/extension', label: '浏览器插件', icon: 'extension' },
  { path: '/settings', label: '设置', icon: 'settings' },
]

async function refreshLlmModel() {
  try {
    if (auth.isAuthenticated) {
      const config = await fetchLlmSettingsApi()
      llmModel.value = String(config.model || '').trim()
    } else {
      const response = await fetch('/api/config')
      const config = await response.json()
      llmModel.value = String(config.llm_model || '').trim()
    }
  } catch {
    llmModel.value = ''
  }
}

function handleLlmSettingsUpdated() {
  void refreshLlmModel()
}

function toggleAppearance(event: Event) {
  isGlassTheme.value = (event.target as HTMLInputElement).checked
  localStorage.setItem(APPEARANCE_STORAGE_KEY, isGlassTheme.value ? 'glass' : 'simple')
}

function startFluidBackground() {
  if (colorbg) return
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  colorbg = new AestheticFluidBg({
    dom: 'box',
    colors: fluidBackgroundColors,
    loop: !prefersReducedMotion,
  })
  colorbg.update('scale', 0.03)
}

function stopFluidBackground() {
  colorbg?.destroy()
  colorbg = null
}

watch(() => auth.token, refreshLlmModel)
watch(isGlassTheme, async (enabled) => {
  if (enabled) {
    await nextTick()
    if (isGlassTheme.value) startFluidBackground()
  } else {
    stopFluidBackground()
  }
})

onMounted(async () => {
  window.addEventListener('llm-settings-updated', handleLlmSettingsUpdated)
  if (isGlassTheme.value) {
    await nextTick()
    startFluidBackground()
  }
  await refreshLlmModel()
})

onBeforeUnmount(() => {
  window.removeEventListener('llm-settings-updated', handleLlmSettingsUpdated)
  stopFluidBackground()
})
</script>

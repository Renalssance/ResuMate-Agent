<template>
  <div :class="['app-shell', isGlassTheme ? 'is-glass-theme' : 'is-simple-theme']">
    <div id="box" class="fluid-bg" aria-hidden="true"></div>

    <dialog ref="navigation" class="app-sidebar" :open="!isCompact" :role="isCompact ? 'dialog' : 'complementary'" aria-label="主导航" :aria-modal="isCompact && drawerOpen || undefined" @close="drawerOpen = false" @click.self="closeNavigation">
      <button v-if="isCompact" class="icon-button navigation-close" type="button" aria-label="关闭导航" @click="closeNavigation"><X class="app-icon" aria-hidden="true" /></button>
      <RouterLink to="/" class="brand" style="color: inherit; text-decoration: none" aria-label="ResuMate 首页">
        <div class="brand-mark" aria-hidden="true"><Cat class="app-icon" /></div>
        <div>
          <strong>ResuMate<span class="workspace-brand-dot">.</span></strong>
          <span>你的招聘好伙伴</span>
        </div>
      </RouterLink>
      <nav class="nav-list">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          class="nav-item"
          :to="item.path"
          @click="closeNavigation"
        >
          <span class="nav-icon" aria-hidden="true"><component :is="item.icon" class="app-icon" /></span>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <MiloStatusBubble :current="agentStatus.current.value" />
      <div v-if="auth.isAuthenticated" class="workspace-account">
        <span class="workspace-avatar" aria-hidden="true">{{ auth.username.slice(0, 1).toUpperCase() }}</span>
        <div><strong>{{ auth.username }}</strong><span>{{ auth.role === 'admin' ? '管理员' : '我的账号' }}</span></div>
        <button type="button" class="workspace-logout" @click="logout" aria-label="退出登录" title="退出登录"><LogOut :size="18" /><span>退出登录</span></button>
      </div>
    </dialog>


    <main class="app-main">
      <header class="topbar">
        <button class="icon-button mobile-only" type="button" aria-label="打开导航" :aria-expanded="drawerOpen" @click="openNavigation">
          <Menu class="app-icon" aria-hidden="true" />
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
      <div :class="['content-wrap', { 'content-reading': ['settings', 'profile-fields'].includes(String(route.name)) }]">
        <RouterView />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ChartNoAxesCombined, CircleHelp, ClipboardList, Cat, Files, LogOut, Menu, Puzzle, ScanSearch, Settings, X } from '@lucide/vue'
import { AestheticFluidBg } from 'color4bg'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchLlmSettingsApi } from '../api/settings'
import { useResponsive } from '../composables/useResponsive'
import { useAgentStatus } from '../composables/useAgentStatus'
import { useAuthStore } from '../stores/auth'
import MiloStatusBubble from './MiloStatusBubble.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const agentStatus = useAgentStatus()
const drawerOpen = ref(false)
const navigation = ref<HTMLDialogElement | null>(null)
const { width } = useResponsive()
const isCompact = computed(() => width.value < 1200)

function openNavigation() {
  navigation.value?.showModal()
  drawerOpen.value = true
}

function closeNavigation() {
  if (isCompact.value) navigation.value?.close()
  drawerOpen.value = false
}

watch(() => route.fullPath, closeNavigation)
watch(isCompact, () => {
  navigation.value?.close()
  drawerOpen.value = false
})
const llmModel = ref<string | null>(null)
const APPEARANCE_STORAGE_KEY = 'resumate:appearance-style'
const isGlassTheme = ref(localStorage.getItem(APPEARANCE_STORAGE_KEY) === 'glass')
const fluidBackgroundColors = ["#FAF7F2", "#EFE2CC", "#D9E8F0", "#B9CFDC", "#DCC8BA", "#FAF7F2"]
let colorbg: AestheticFluidBg | null = null
const motionPreferences = window.matchMedia('(prefers-reduced-motion: reduce), (prefers-reduced-transparency: reduce), (prefers-contrast: more)')
function syncFluidPreferences() {
  stopFluidBackground()
  if (isGlassTheme.value) startFluidBackground()
}

const navItems = [
  { path: '/documents', label: '文档管理', icon: Files },
  { path: '/matching', label: '岗位匹配', icon: ScanSearch },
  { path: '/profile-fields', label: '结构资料', icon: ClipboardList },
  { path: '/questions', label: '试题生成', icon: CircleHelp },
  { path: '/applications', label: '投递记录', icon: ChartNoAxesCombined },
  { path: '/extension', label: '浏览器插件', icon: Puzzle },
  { path: '/settings', label: '设置', icon: Settings },
]

function logout() {
  auth.logout()
  closeNavigation()
  void router.push('/')
}

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
  if (prefersReducedMotion || window.matchMedia('(prefers-reduced-transparency: reduce), (prefers-contrast: more)').matches) return
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
  motionPreferences.addEventListener('change', syncFluidPreferences)
  if (isGlassTheme.value) {
    await nextTick()
    startFluidBackground()
  }
  await refreshLlmModel()
})

onBeforeUnmount(() => {
  window.removeEventListener('llm-settings-updated', handleLlmSettingsUpdated)
  motionPreferences.removeEventListener('change', syncFluidPreferences)
  stopFluidBackground()
})
</script>

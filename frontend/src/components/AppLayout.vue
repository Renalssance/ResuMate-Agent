<template>
  <div class="app-shell">
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
          <span class="nav-icon">{{ item.icon }}</span>
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>

    <div v-if="drawerOpen" class="drawer-mask" @click="drawerOpen = false"></div>

    <main class="app-main">
      <header class="topbar">
        <button class="icon-button mobile-only" type="button" aria-label="打开导航" @click="drawerOpen = true">
          ☰
        </button>
        <div class="topbar-title">
          <h1>{{ route.meta.title }}</h1>
          <p>{{ route.meta.description }}</p>
        </div>

        <form v-if="!auth.isAuthenticated" class="auth-form" @submit.prevent="submitAuth('login')">
          <input v-model="username" type="text" autocomplete="username" placeholder="用户名" aria-label="用户名" />
          <input v-model="password" type="password" autocomplete="current-password" placeholder="密码" aria-label="密码" />
          <button class="button-primary" type="submit" :disabled="auth.loading">登录</button>
          <button class="button-secondary" type="button" :disabled="auth.loading" @click="submitAuth('register')">
            注册
          </button>
          <span v-if="auth.error" class="auth-error">{{ auth.error }}</span>
        </form>

        <div v-else class="auth-user">
          <span class="status-dot"></span>
          <span>{{ auth.username }}</span>
          <button class="button-secondary" type="button" @click="auth.logout()">退出</button>
        </div>
      </header>
      <div class="content-wrap">
        <RouterView />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

type AuthMode = 'login' | 'register'

const route = useRoute()
const auth = useAuthStore()
const drawerOpen = ref(false)
const username = ref('')
const password = ref('')

const navItems = [
  { path: '/documents', label: '文档管理', icon: '文' },
  { path: '/matching', label: '岗位匹配', icon: '配' },
  { path: '/questions', label: '试题生成', icon: '题' },
  { path: '/follow-up', label: '追问模拟', icon: '问' },
]

async function submitAuth(mode: AuthMode) {
  await auth.submit(mode, { username: username.value, password: password.value })
  password.value = ''
}
</script>

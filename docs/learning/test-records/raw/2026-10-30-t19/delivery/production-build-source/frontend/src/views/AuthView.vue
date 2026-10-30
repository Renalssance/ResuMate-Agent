<template>
  <div class="rm-public rm-auth-page">
    <header class="rm-header rm-container"><BrandLogo /><RouterLink class="rm-back" to="/"><ArrowLeft :size="16" /> 返回首页</RouterLink></header>
    <main class="rm-auth-main rm-container">
      <div class="rm-auth-welcome"><span class="rm-eyebrow">YOUR NEXT CHAPTER STARTS HERE</span><h1>每个闪光点，<br>都值得被看见。</h1><img src="/images/milo-welcome.png" alt="米洛举爪欢迎你" width="1300" height="1200"><p>米洛已就位，准备陪你迈出下一步。</p></div>
      <section class="rm-auth-card" aria-labelledby="auth-title">
        <span class="rm-eyebrow">{{ isRegister ? 'HELLO, NEW FRIEND' : 'WELCOME BACK' }}</span>
        <h2 id="auth-title">{{ isRegister ? '和米洛成为伙伴' : '欢迎回到 ResuMate' }}</h2>
        <p>{{ isRegister ? '创建账号，开启你的招聘工作台。' : '登录账号，继续上一次的探索。' }}</p>
        <template v-if="auth.isAuthenticated"><p>你已登录为 {{ auth.username }}。</p><RouterLink class="rm-button" to="/documents">进入工作台 <ArrowRight :size="18" /></RouterLink></template>
        <form v-else :aria-busy="auth.loading" @submit.prevent="submit">
          <label for="auth-username">用户名</label>
          <input id="auth-username" v-model.trim="username" name="username" autocomplete="username" required placeholder="输入你的用户名" :disabled="auth.loading">
          <label for="auth-password">密码</label>
          <div class="rm-password-field"><input id="auth-password" v-model="password" :aria-describedby="error ? 'auth-error' : undefined" name="password" :type="showPassword ? 'text' : 'password'" :autocomplete="isRegister ? 'new-password' : 'current-password'" required placeholder="输入你的密码" :disabled="auth.loading"><button type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" :aria-pressed="showPassword" @click="showPassword = !showPassword"><component :is="showPassword ? EyeOff : Eye" :size="18" /></button></div>
          <template v-if="isRegister"><label for="auth-confirm">确认密码</label><input id="auth-confirm" v-model="confirmation" name="confirmation" type="password" autocomplete="new-password" required placeholder="再次输入密码" :disabled="auth.loading"></template>
          <p v-if="error" id="auth-error" class="rm-auth-error" role="alert">{{ error }}</p>
          <button class="rm-button rm-submit" type="submit" :disabled="auth.loading">{{ auth.loading ? '正在处理…' : isRegister ? '注册并开始使用' : '登录' }}<ArrowRight v-if="!auth.loading" :size="18" /></button>
          <p class="rm-auth-switch">{{ isRegister ? '已有账号？' : '还没有账号？' }} <RouterLink :to="isRegister ? '/login' : '/register'">{{ isRegister ? '去登录' : '注册账号' }}</RouterLink></p>
        </form>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowRight, Eye, EyeOff } from '@lucide/vue'
import BrandLogo from '../components/BrandLogo.vue'
import { useAuthStore } from '../stores/auth'
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const isRegister = computed(() => route.name === 'register')
const username = ref('')
const password = ref('')
const confirmation = ref('')
const showPassword = ref(false)
const error = ref('')
watch(isRegister, () => { error.value = ''; password.value = ''; confirmation.value = ''; showPassword.value = false })
async function submit() {
  if (auth.loading) return
  error.value = ''
  if (!username.value.trim()) { error.value = '请输入用户名。'; return }
  if (isRegister.value && password.value !== confirmation.value) { error.value = '两次输入的密码不一致，请重新确认。'; return }
  try {
    await auth.submit(isRegister.value ? 'register' : 'login', { username: username.value, password: password.value })
    password.value = ''; confirmation.value = ''
    await router.push(isRegister.value ? '/settings' : '/documents')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '暂时无法登录，请稍后重试。'
  }
}
</script>

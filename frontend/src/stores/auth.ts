import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { loginApi, registerApi } from '../api/auth'
import { clearAccessToken, readAccessToken, saveAccessToken } from '../services/authToken'

type AuthMode = 'login' | 'register'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(readAccessToken())
  const username = ref(localStorage.getItem('username') || '')
  const role = ref(localStorage.getItem('role') || '')
  const loading = ref(false)
  const error = ref('')

  const isAuthenticated = computed(() => Boolean(token.value))

  async function submit(mode: AuthMode, credentials: { username: string; password: string }) {
    loading.value = true
    error.value = ''
    try {
      const request = {
        username: credentials.username.trim(),
        password: credentials.password,
        role: 'user' as const,
      }
      const response = mode === 'login' ? await loginApi(request) : await registerApi(request)
      token.value = response.access_token
      username.value = response.username
      role.value = response.role
      saveAccessToken(response.access_token)
      localStorage.setItem('username', response.username)
      localStorage.setItem('role', response.role)
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  function logout() {
    token.value = ''
    username.value = ''
    role.value = ''
    clearAccessToken()
    localStorage.removeItem('username')
    localStorage.removeItem('role')
  }

  return {
    token,
    username,
    role,
    loading,
    error,
    isAuthenticated,
    submit,
    logout,
  }
})

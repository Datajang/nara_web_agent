// 인증 상태 (SPEC §10.6). 토큰은 httpOnly 쿠키라 JS는 사용자 정보만 든다.
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi, type Me } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const me = ref<Me | null>(null)
  const ready = ref(false)
  let loading: Promise<void> | null = null

  const isAdmin = computed(() => me.value?.role === 'admin')

  /** 첫 진입 때 한 번 GET /me로 상태를 확정한다(만료된 access는 client가 refresh). */
  function ensureLoaded(): Promise<void> {
    if (ready.value) return Promise.resolve()
    loading ??= authApi
      .me()
      .then((m) => {
        me.value = m
      })
      .catch(() => {
        me.value = null
      })
      .finally(() => {
        ready.value = true
        loading = null
      })
    return loading
  }

  async function login(email: string, password: string): Promise<Me> {
    const m = await authApi.login(email, password)
    me.value = m
    ready.value = true
    return m
  }

  async function logout(): Promise<void> {
    try {
      await authApi.logout()
    } finally {
      clear()
    }
  }

  function clear(): void {
    me.value = null
    ready.value = true
  }

  return { me, ready, isAdmin, ensureLoaded, login, logout, clear }
})

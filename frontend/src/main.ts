import 'pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css'
import './styles/base.css'

import { createPinia } from 'pinia'
import { createApp } from 'vue'
import { clientHooks } from '@/api/client'
import { copy } from '@/copy'
import { createAppRouter } from '@/router'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import App from './App.vue'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
const router = createAppRouter()
app.use(router)

// 세션 만료: 스토어를 비우고 로그인 화면으로 (§10.7)
clientHooks.onUnauthorized = () => {
  useAuthStore(pinia).clear()
  const here = router.currentRoute.value
  if (here.path !== '/login') {
    useUiStore(pinia).toast(copy.common.sessionExpired, 'warning')
    void router.replace({ path: '/login', query: { next: here.fullPath } })
  }
}
clientHooks.onRateLimited = (seconds) => {
  useUiStore(pinia).toast(copy.common.rateLimited(seconds), 'warning')
}

app.mount('#app')

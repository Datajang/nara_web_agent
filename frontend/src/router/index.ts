// 라우터와 가드 (SPEC §10.7). 화면은 라우트 단위로 코드 분할한다.
import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'
import { copy } from '@/copy'
import { useAuthStore } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    requiresAdmin?: boolean
    guestOnly?: boolean
    title?: string
  }
}

const ComingSoon = () => import('@/views/ComingSoonView.vue')

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/search' },
  {
    path: '/login',
    component: () => import('@/views/auth/LoginView.vue'),
    meta: { guestOnly: true, title: copy.auth.loginTitle },
  },
  {
    path: '/register',
    component: () => import('@/views/auth/RegisterView.vue'),
    meta: { guestOnly: true, title: copy.auth.registerTitle },
  },
  {
    path: '/register/check-email',
    component: () => import('@/views/auth/CheckEmailView.vue'),
    meta: { title: copy.auth.checkEmailTitle },
  },
  {
    path: '/verify-email',
    component: () => import('@/views/auth/VerifyEmailView.vue'),
    meta: { title: copy.auth.verifyingTitle },
  },
  {
    path: '/pending-approval',
    component: () => import('@/views/auth/PendingApprovalView.vue'),
    meta: { title: copy.auth.pendingApprovalTitle },
  },
  {
    path: '/forgot-password',
    component: () => import('@/views/auth/ForgotPasswordView.vue'),
    meta: { title: copy.auth.forgotTitle },
  },
  {
    path: '/reset-password',
    component: () => import('@/views/auth/ResetPasswordView.vue'),
    meta: { title: copy.auth.resetTitle },
  },
  {
    path: '/',
    component: () => import('@/components/layout/AppShell.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: 'search', component: ComingSoon, meta: { title: copy.nav.search } },
      { path: 'recommend', component: ComingSoon, meta: { title: copy.nav.recommend } },
      { path: 'assistant', component: ComingSoon, meta: { title: copy.nav.assistant } },
      { path: 'library', component: ComingSoon, meta: { title: copy.nav.library } },
      { path: 'settings', component: ComingSoon, meta: { title: copy.nav.settings } },
      {
        path: 'admin/users',
        component: () => import('@/views/admin/UsersView.vue'),
        meta: { requiresAdmin: true, title: copy.admin.usersTitle },
      },
      ...(import.meta.env.DEV
        ? [
            {
              path: 'dev/components',
              component: () => import('@/views/dev/ComponentsView.vue'),
              meta: { title: copy.dev.title },
            },
          ]
        : []),
      {
        path: ':pathMatch(.*)*',
        component: () => import('@/views/NotFoundView.vue'),
        meta: { title: copy.page.notFoundTitle },
      },
    ],
  },
]

/** next 쿼리는 같은 앱 안의 경로만 허용한다(오픈 리다이렉트 방지). */
export function safeNext(next: unknown): string {
  return typeof next === 'string' && next.startsWith('/') && !next.startsWith('//')
    ? next
    : '/search'
}

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  const router = createRouter({ history, routes })

  router.beforeEach(async (to) => {
    const auth = useAuthStore()
    await auth.ensureLoaded()
    const needsAuth = to.matched.some((r) => r.meta.requiresAuth)
    if (needsAuth && !auth.me) return { path: '/login', query: { next: to.fullPath } }
    if (to.matched.some((r) => r.meta.requiresAdmin) && !auth.isAdmin) return '/search'
    if (to.meta.guestOnly && auth.me) return '/search'
    return true
  })

  router.afterEach((to) => {
    if (typeof document !== 'undefined') {
      document.title = to.meta.title ? `${to.meta.title} · ${copy.app.name}` : copy.app.name
    }
  })

  return router
}

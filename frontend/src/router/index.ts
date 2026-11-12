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

const routes: RouteRecordRaw[] = [
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
      { path: '', component: () => import('@/views/HomeView.vue'), meta: { title: copy.feed.title } },
      {
        path: 'onboarding',
        component: () => import('@/views/OnboardingView.vue'),
        meta: { title: copy.onboarding.title },
      },
      { path: 'join', component: () => import('@/views/JoinView.vue'), meta: { title: copy.team.joinTitle } },
      { path: 'search', component: () => import('@/views/SearchView.vue'), meta: { title: copy.nav.search } },
      {
        path: 'recommend',
        component: () => import('@/views/RecommendView.vue'),
        meta: { title: copy.nav.recommend },
      },
      {
        path: 'bids/:bidId',
        component: () => import('@/views/BidDetailView.vue'),
        meta: { title: copy.detail.analyzeTitle },
      },
      {
        path: 'assistant/:conversationId?',
        component: () => import('@/views/AssistantView.vue'),
        meta: { title: copy.nav.assistant },
      },
      { path: 'library', component: () => import('@/views/LibraryView.vue'), meta: { title: copy.nav.library } },
      { path: 'settings', redirect: '/settings/profiles' },
      {
        path: 'settings/profiles',
        component: () => import('@/views/settings/ProfilesView.vue'),
        meta: { title: copy.profile.title },
      },
      {
        path: 'settings/team',
        component: () => import('@/views/settings/TeamView.vue'),
        meta: { title: copy.team.title },
      },
      {
        path: 'settings/account',
        component: () => import('@/views/settings/AccountView.vue'),
        meta: { title: copy.account.title },
      },
      {
        path: 'admin/users',
        component: () => import('@/views/admin/UsersView.vue'),
        meta: { requiresAdmin: true, title: copy.admin.usersTitle },
      },
      {
        path: 'admin/usage',
        component: () => import('@/views/admin/UsageView.vue'),
        meta: { requiresAdmin: true, title: copy.admin.usageTitle },
      },
      {
        path: 'admin/collector',
        component: () => import('@/views/admin/CollectorView.vue'),
        meta: { requiresAdmin: true, title: copy.admin.collectorTitle },
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
    : '/'
}

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  const router = createRouter({ history, routes })

  router.beforeEach(async (to) => {
    const auth = useAuthStore()
    await auth.ensureLoaded()
    const needsAuth = to.matched.some((r) => r.meta.requiresAuth)
    if (needsAuth && !auth.me) return { path: '/login', query: { next: to.fullPath } }
    // 관리자 경로의 비관리자는 주소를 유지한 채 403 화면(AppShell이 표시, §7.11-9)
    if (to.meta.guestOnly && auth.me) return '/'
    return true
  })

  router.afterEach((to) => {
    if (typeof document !== 'undefined') {
      document.title = to.meta.title ? `${to.meta.title} · ${copy.app.name}` : copy.app.name
    }
  })

  return router
}

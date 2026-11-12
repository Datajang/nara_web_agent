// §10.7 라우터 가드: 첫 진입 때 GET /me로 인증 상태를 확정한다.
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { copy } from '@/copy'
import { createAppRouter } from '@/router'

function meResponse(me: unknown) {
  return vi.fn(async (url: string) => {
    if (url === '/api/v1/me' && me) return new Response(JSON.stringify(me), { status: 200 })
    return new Response('{"error":{"code":"unauthorized","message":"","details":[]}}', { status: 401 })
  })
}

const MEMBER = { id: 1, email: 'a@corp.example', display_name: 'a', role: 'member', status: 'active' }
const ADMIN = { ...MEMBER, role: 'admin' }

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.unstubAllGlobals())

async function go(path: string, me: unknown) {
  setActivePinia(createPinia()) // 호출마다 새 세션
  vi.stubGlobal('fetch', meResponse(me))
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  return router.currentRoute.value
}

describe('router guard', () => {
  it('비로그인은 로그인 화면으로, next 유지', async () => {
    const r = await go('/library?tab=bookmarks', null)
    expect(r.path).toBe('/login')
    expect(r.query.next).toBe('/library?tab=bookmarks')
  })

  it('로그인 사용자는 보호 화면에 들어간다', async () => {
    expect((await go('/search', MEMBER)).path).toBe('/search')
  })

  it('회원이 관리자 화면에 가면 검색으로', async () => {
    expect((await go('/admin/users', MEMBER)).path).toBe('/admin/users') // 403 화면은 AppShell이 표시
    expect((await go('/admin/users', ADMIN)).path).toBe('/admin/users')
  })

  it('로그인 사용자가 로그인 화면에 가면 홈(관심 공고)으로 (§13 P6)', async () => {
    expect((await go('/login', MEMBER)).path).toBe('/')
  })

  it('공개 화면은 비로그인도 열린다', async () => {
    for (const p of ['/register', '/verify-email?token=x', '/forgot-password', '/pending-approval']) {
      expect((await go(p, null)).path).toBe(p.split('?')[0])
    }
  })

  it('/ 는 관심 공고 홈이다 (§13 P6)', async () => {
    const r = await go('/', MEMBER)
    expect(r.path).toBe('/')
    expect(r.meta.title).toBe(copy.feed.title)
  })
})

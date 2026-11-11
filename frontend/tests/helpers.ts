// 화면 테스트 공용: fetch 경로별 가짜 응답(SSE 포함)과 앱 마운트.
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, type Router } from 'vue-router'
import { vi } from 'vitest'
import type { BidCard } from '@/api/types'
import App from '@/App.vue'
import { createAppRouter } from '@/router'

export const MEMBER = {
  id: 1,
  email: 'a@corp.example',
  display_name: '에이',
  role: 'member',
  status: 'active',
}
export const ADMIN = { ...MEMBER, role: 'admin' }

export type Reply = Response | ((init: RequestInit, url: string) => Response | Promise<Response>)

export function json(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  })
}

/** SSE 응답. 이벤트 객체 배열을 `data: {json}` 블록으로 보낸다. */
export function sse(events: unknown[], { delayMs = 0, close = true } = {}) {
  const enc = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    async start(controller) {
      for (const e of events) {
        if (delayMs) await new Promise((r) => setTimeout(r, delayMs))
        controller.enqueue(enc.encode(`data: ${JSON.stringify(e)}\n\n`))
      }
      if (close) controller.close()
    },
  })
  return new Response(body, { status: 200, headers: { 'content-type': 'text/event-stream' } })
}

export interface Call {
  method: string
  url: string
  body: unknown
}

/**
 * 키는 "METHOD /api/v1/경로"(쿼리 제외). 값은 응답 또는 함수.
 * 등록하지 않은 경로는 404. /me는 기본으로 me를 돌려준다.
 */
export function mockApi(routes: Record<string, Reply>, me: unknown = MEMBER) {
  const calls: Call[] = []
  const fetchMock = vi.fn(async (url: string, init: RequestInit = {}) => {
    const method = (init.method ?? 'GET').toUpperCase()
    const path = url.split('?')[0]
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : undefined
    calls.push({ method, url, body })
    const reply = routes[`${method} ${path}`]
    if (reply) return typeof reply === 'function' ? reply(init, url) : reply.clone()
    if (path === '/api/v1/me' && method === 'GET') {
      return me ? json(me) : json({ error: { code: 'unauthorized', message: '' } }, 401)
    }
    return json({ error: { code: 'not_found', message: '', details: [] } }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  return { calls, fetchMock }
}

export interface Mounted {
  wrapper: VueWrapper
  router: Router
}

export async function mountAt(path: string): Promise<Mounted> {
  setActivePinia(createPinia())
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  })
  const wrapper = mount(App, {
    global: { plugins: [router, [VueQueryPlugin, { queryClient }]] },
    attachTo: document.body,
  })
  await settle()
  return { wrapper, router }
}

/** 프라미스·스트림이 끝날 때까지 몇 번 돌린다. */
export async function settle(times = 6) {
  for (let i = 0; i < times; i++) {
    await flushPromises()
    await new Promise((r) => setTimeout(r, 0))
  }
}

export function card(over: Partial<BidCard> = {}): BidCard {
  return {
    bid_id: 'b101',
    source: 'regular',
    bid_no: 'R26BK00000101',
    title: 'AI 민원 분석 시스템 구축',
    org_name: '행정안전부',
    budget: 120000000,
    deadline_at: '2026-11-20T01:00:00Z',
    notice_at: '2026-11-08T23:10:00Z',
    status: 'open',
    cancelled: false,
    revision: 1,
    detail_url: 'https://www.g2b.go.kr/link/x',
    has_files: true,
    summary_ready: false,
    bookmarked: false,
    score: null,
    reason: null,
    ...over,
  } as BidCard
}

export function profile(over: Record<string, unknown> = {}) {
  return {
    id: 7,
    name: '우리 팀',
    description: 'AI 플랫폼 개발팀',
    keywords: ['AI'],
    is_default: true,
    profile_hash: 'h',
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
    ...over,
  }
}

export const text = (w: VueWrapper) => (w.element as HTMLElement).textContent ?? ''

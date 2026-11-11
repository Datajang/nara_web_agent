// §13.4 게이트: 로그인 화면이 키보드만으로 조작되고 접근성 위반이 없다. 실패 문구는 하나로 통일.
import axe from 'axe-core'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, type Router } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { copy } from '@/copy'
import { createAppRouter } from '@/router'
import App from '@/App.vue'

let wrapper: VueWrapper | null = null
let router: Router

function respond(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers })
}

async function mountLogin(loginResponse: () => Response) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url === '/api/v1/auth/login') return loginResponse()
      if (url === '/api/v1/me') return respond(401, { error: { code: 'unauthorized' } })
      return respond(401, { error: { code: 'unauthorized' } })
    }),
  )
  setActivePinia(createPinia())
  router = createAppRouter(createMemoryHistory())
  await router.push('/login?next=/library')
  wrapper = mount(App, { global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return wrapper
}

async function submit(w: VueWrapper, email = 'a@corp.example', pw = 'some-password-1') {
  await w.get('input[type="email"]').setValue(email)
  await w.get('input[type="password"]').setValue(pw)
  await w.get('form').trigger('submit')
  await flushPromises()
}

beforeEach(() => {
  document.body.innerHTML = ''
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  vi.unstubAllGlobals()
})

describe('LoginView', () => {
  it('라벨이 보이고 입력과 연결된다', async () => {
    const w = await mountLogin(() => respond(200, {}))
    const email = w.get('input[type="email"]')
    const label = w.get(`label[for="${email.attributes('id')}"]`)
    expect(label.text()).toBe(copy.auth.email)
    expect(email.attributes('autocomplete')).toBe('email')
    expect(w.get('input[type="password"]').attributes('autocomplete')).toBe('current-password')
  })

  it('포커스 순서: 이메일 → 비밀번호 → 로그인 버튼 → 보조 링크', async () => {
    const w = await mountLogin(() => respond(200, {}))
    const focusables = Array.from(
      (w.element as HTMLElement).querySelectorAll<HTMLElement>('main a[href], main button, main input'),
    ).filter((el) => el.tabIndex >= 0)
    const kinds = focusables.map((el) =>
      el.tagName === 'INPUT' ? (el as HTMLInputElement).type : el.tagName.toLowerCase(),
    )
    expect(kinds.slice(0, 3)).toEqual(['email', 'password', 'button'])
    expect(kinds.slice(3).every((k) => k === 'a')).toBe(true)
    expect(focusables.every((el) => el.tabIndex === 0)).toBe(true) // 양수 tabindex 없음
  })

  it('axe 위반 없음 (jsdom이라 색 대비는 contrast.test.ts가 맡는다)', async () => {
    const w = await mountLogin(() => respond(200, {}))
    const result = await axe.run(w.element as HTMLElement, {
      rules: { 'color-contrast': { enabled: false } },
    })
    expect(result.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([])
  })

  it('실패 문구는 이메일 존재 여부와 무관하게 하나', async () => {
    const w = await mountLogin(() =>
      respond(401, { error: { code: 'invalid_credentials', message: '', details: [] } }),
    )
    await submit(w)
    const alert = w.get('[role="alert"]')
    expect(alert.text()).toBe(copy.auth.invalid)
  })

  it('잠김(429 account_locked)은 잠김 문구', async () => {
    const w = await mountLogin(() =>
      respond(429, { error: { code: 'account_locked', message: '', details: [] } }, { 'Retry-After': '900' }),
    )
    await submit(w)
    expect(w.get('[role="alert"]').text()).toBe(copy.auth.locked)
  })

  it('승인 대기 계정은 승인 대기 화면으로', async () => {
    const w = await mountLogin(() =>
      respond(403, { error: { code: 'pending_approval', message: '', details: [] } }),
    )
    await submit(w)
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/pending-approval'))
  })

  it('성공하면 next로 이동', async () => {
    const me = { id: 1, email: 'a@corp.example', display_name: 'a', role: 'member', status: 'active' }
    const w = await mountLogin(() => respond(200, me))
    await submit(w)
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/library'))
  })
})

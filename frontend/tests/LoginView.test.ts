// §13.4 게이트: 로그인 화면이 키보드만으로 조작되고 접근성 위반이 없다. 실패 문구는 하나로 통일.
import axe from 'axe-core'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
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
  wrapper = mount(App, {
    global: { plugins: [router, [VueQueryPlugin, { queryClient: new QueryClient() }]] },
    attachTo: document.body,
  })
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
  localStorage.clear()
})

const REMEMBER_KEY = 'nara.login.email'
const ME = { id: 1, email: 'a@corp.example', display_name: 'a', role: 'member', status: 'active' }
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

  it('포커스 순서: 이메일 → 비밀번호 → 이메일 기억하기 → 로그인 버튼 → 보조 링크', async () => {
    const w = await mountLogin(() => respond(200, {}))
    const focusables = Array.from(
      (w.element as HTMLElement).querySelectorAll<HTMLElement>('main a[href], main button, main input'),
    ).filter((el) => el.tabIndex >= 0)
    const kinds = focusables.map((el) =>
      el.tagName === 'INPUT' ? (el as HTMLInputElement).type : el.tagName.toLowerCase(),
    )
    expect(kinds.slice(0, 4)).toEqual(['email', 'password', 'checkbox', 'button'])
    expect(kinds.slice(4).every((k) => k === 'a')).toBe(true)
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
    const w = await mountLogin(() => respond(200, ME))
    await submit(w)
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/library'), { timeout: 5000 })
  })
})

// 이메일 기억하기 (2026-11-24 운영 피드백): 이메일만 이 브라우저에 남긴다. 비밀번호·토큰은 저장하지 않는다(§9).
describe('LoginView 이메일 기억하기', () => {
  const checkbox = (w: VueWrapper) => w.get<HTMLInputElement>('input[type="checkbox"]')

  it('기본은 꺼져 있고 라벨로 읽힌다', async () => {
    const w = await mountLogin(() => respond(200, ME))
    expect(checkbox(w).element.checked).toBe(false)
    expect(checkbox(w).element.closest('label')?.textContent?.trim()).toBe(copy.auth.rememberEmail)
    expect((w.get('input[type="email"]').element as HTMLInputElement).value).toBe('')
  })

  it('켜고 로그인에 성공하면 이메일만 저장한다', async () => {
    const w = await mountLogin(() => respond(200, ME))
    await checkbox(w).setValue(true)
    await submit(w, '  a@corp.example ', 'some-password-1')
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/library'), { timeout: 5000 })
    expect(localStorage.getItem(REMEMBER_KEY)).toBe('a@corp.example')
    expect(JSON.stringify({ ...localStorage })).not.toContain('some-password-1')
  })

  it('로그인에 실패하면 저장하지 않는다', async () => {
    const w = await mountLogin(() =>
      respond(401, { error: { code: 'invalid_credentials', message: '', details: [] } }),
    )
    await checkbox(w).setValue(true)
    await submit(w)
    expect(localStorage.getItem(REMEMBER_KEY)).toBeNull()
  })

  it('저장된 이메일이 있으면 채워 두고, 체크된 채로 비밀번호 칸에 커서를 둔다', async () => {
    localStorage.setItem(REMEMBER_KEY, 'saved@corp.example')
    const w = await mountLogin(() => respond(200, ME))
    expect((w.get('input[type="email"]').element as HTMLInputElement).value).toBe('saved@corp.example')
    expect(checkbox(w).element.checked).toBe(true)
    expect(document.activeElement).toBe(w.get('input[type="password"]').element)
  })

  it('체크를 풀면 로그인하지 않아도 바로 지운다', async () => {
    localStorage.setItem(REMEMBER_KEY, 'saved@corp.example')
    const w = await mountLogin(() => respond(200, ME))
    await checkbox(w).setValue(false)
    expect(localStorage.getItem(REMEMBER_KEY)).toBeNull()
  })

  it('끄고 로그인하면 예전에 저장한 이메일도 지운다', async () => {
    localStorage.setItem(REMEMBER_KEY, 'old@corp.example')
    const w = await mountLogin(() => respond(200, ME))
    await checkbox(w).setValue(false)
    await submit(w)
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/library'), { timeout: 5000 })
    expect(localStorage.getItem(REMEMBER_KEY)).toBeNull()
  })

  it('저장소가 막혀도(사생활 보호 창) 로그인은 된다', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('SecurityError')
    })
    const w = await mountLogin(() => respond(200, ME))
    await checkbox(w).setValue(true)
    await submit(w)
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/library'), { timeout: 5000 })
    vi.restoreAllMocks()
  })
})

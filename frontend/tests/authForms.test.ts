// 2026-11-23 사용자 요청: 가입·새 비밀번호에 '비밀번호 확인' 칸, 로그인 화면의 '비밀번호 찾기'를 잘 보이게.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { copy } from '@/copy'
import { json, mockApi, mountAt, settle, type Mounted } from './helpers'

let m: Mounted | null = null
beforeEach(() => {
  document.body.innerHTML = ''
})
afterEach(() => {
  m?.wrapper.unmount()
  m = null
  vi.unstubAllGlobals()
})

async function fillAndSubmit(w: Mounted['wrapper'], pw: string, confirm: string) {
  const pws = w.findAll('input[type="password"]')
  expect(pws).toHaveLength(2)
  await pws[0]!.setValue(pw)
  await pws[1]!.setValue(confirm)
  await w.get('form').trigger('submit')
  await settle()
}

describe('가입: 비밀번호 확인', () => {
  it('두 칸이 다르면 보내지 않고 확인 칸에 안내한다', async () => {
    const api = mockApi({ 'POST /api/v1/auth/register': json({}, 201) }, null)
    m = await mountAt('/register')
    await m.wrapper.get('input[type="email"]').setValue('kim@cslee.co.kr')
    await fillAndSubmit(m.wrapper, 'correct-horse-1', 'correct-horse-2')
    expect(api.calls.some((c) => c.url === '/api/v1/auth/register')).toBe(false)
    expect(m.wrapper.text()).toContain(copy.auth.passwordMismatch)
    const confirm = m.wrapper.findAll('input[type="password"]')[1]!
    expect(confirm.attributes('aria-invalid')).toBe('true')
    expect(confirm.attributes('autocomplete')).toBe('new-password')
  })

  it('같으면 가입을 보낸다', async () => {
    const api = mockApi({ 'POST /api/v1/auth/register': json({}, 201) }, null)
    m = await mountAt('/register')
    await m.wrapper.get('input[type="email"]').setValue('kim@cslee.co.kr')
    await fillAndSubmit(m.wrapper, 'correct-horse-1', 'correct-horse-1')
    const call = api.calls.find((c) => c.url === '/api/v1/auth/register')!
    expect(call.body).toMatchObject({ email: 'kim@cslee.co.kr', password: 'correct-horse-1' })
  })
})

describe('새 비밀번호: 비밀번호 확인', () => {
  it('두 칸이 다르면 보내지 않는다, 같으면 보낸다', async () => {
    const api = mockApi({ 'POST /api/v1/auth/password/reset': json({}, 200) }, null)
    m = await mountAt('/reset-password?token=abc')
    await fillAndSubmit(m.wrapper, 'correct-horse-1', 'different-1')
    expect(api.calls.some((c) => c.url === '/api/v1/auth/password/reset')).toBe(false)
    expect(m.wrapper.text()).toContain(copy.auth.passwordMismatch)
    await fillAndSubmit(m.wrapper, 'correct-horse-1', 'correct-horse-1')
    expect(api.calls.some((c) => c.url === '/api/v1/auth/password/reset')).toBe(true)
  })
})

describe('로그인: 비밀번호 찾기', () => {
  it('로그인 버튼 바로 아래에 비밀번호 찾기 링크', async () => {
    mockApi({}, null)
    m = await mountAt('/login')
    const link = m.wrapper.get('form a[href="/forgot-password"]')
    expect(link.text()).toBe(copy.auth.toForgot)
    expect(copy.auth.toForgot).toBe('비밀번호 찾기')
  })
})

// P2 브라우저 게이트 스크립트 (SPEC §13.4). CI에는 아직 없다(@playwright/test 전환은 P4).
// 실행 방법과 Debian 11 환경 메모: docs/decisions/2026-11-11-p2-auth.md
//   백엔드: ENV=development MAIL_BACKEND=memory APP_ORIGIN=http://localhost:5173 COOKIE_SECURE=false
//           uvicorn app.main:app --port 8020   (관리자: e2e-admin@corp.example를 create_admin으로 미리 생성)
//   프론트: VITE_API_TARGET=http://127.0.0.1:8020 npx vite --port 5173
//   실행:   playwright 1.65가 설치된 곳에서 node e2e/p2-auth-flow.mjs  (스크린샷은 e2e/shots/)
// P2 브라우저 게이트: 가입 → 메일 링크 → 승인 → 로그인 → 새로고침 유지 → 로그아웃, 키보드 로그인, 대비.
import { chromium } from 'playwright'

const BASE = 'http://localhost:5173'
const OUT = new URL('./shots/', import.meta.url).pathname
const USER = `e2e-user-${Date.now()}@corp.example`
const PW = 'e2e-user-password-1'
const ADMIN = 'e2e-admin@corp.example'
const ADMIN_PW = 'e2e-admin-password-1'
const results = []
const ok = (name, cond, extra = '') => {
  results.push(`${cond ? 'PASS' : 'FAIL'}  ${name}${extra ? ' — ' + extra : ''}`)
  if (!cond) process.exitCode = 1
}

const browser = await chromium.launch()
const userCtx = await browser.newContext({ viewport: { width: 1280, height: 800 } })
const page = await userCtx.newPage()
const consoleErrors = []
// 401·403 응답의 'Failed to load resource'는 의도된 흐름이라 제외
page.on('console', (m) => m.type() === 'error' && !m.text().startsWith('Failed to load resource') && consoleErrors.push(m.text()))

// 1. 가입
await page.goto(`${BASE}/register`)
await page.getByLabel('이메일').fill(USER)
await page.getByLabel('이름').fill('이투이')
await page.getByLabel('비밀번호').fill(PW)
await page.getByRole('button', { name: '가입하기' }).click()
await page.waitForURL('**/register/check-email**')
ok('가입 → 메일 확인 안내', await page.getByText('메일을 확인해 주세요').isVisible())
await page.screenshot({ path: `${OUT}01-check-email.png` })

// 2. 메일 링크 (MAIL_BACKEND=memory, 개발 전용 메일함)
const mails = (await (await page.request.get(`${BASE}/api/v1/_dev/mail`)).json()).items
const mail = mails.filter((m) => m.to === USER).at(-1)
const link = mail?.body.match(/https?:\/\/\S+verify-email\?token=\S+/)?.[0]
ok('인증 메일 도착', Boolean(link), mail?.subject)

// 인증 전 로그인 → 메일 확인 화면
await page.goto(`${BASE}/login`)
await page.getByLabel('이메일').fill(USER)
await page.getByLabel('비밀번호').fill(PW)
await page.getByRole('button', { name: '로그인' }).click()
await page.waitForURL('**/register/check-email**')
ok('인증 전 로그인 → 메일 확인 안내', true)

await page.goto(link)
await page.getByText('승인을 기다리고 있어요').waitFor()
ok('메일 링크 → 승인 대기', true)
await page.screenshot({ path: `${OUT}02-verified-pending.png` })

// 승인 전 로그인 → 승인 대기 화면
await page.goto(`${BASE}/login`)
await page.getByLabel('이메일').fill(USER)
await page.getByLabel('비밀번호').fill(PW)
await page.getByRole('button', { name: '로그인' }).click()
await page.waitForURL('**/pending-approval')
ok('승인 전 로그인 → 승인 대기 화면', true)

// 3. 관리자 승인
const adminCtx = await browser.newContext({ viewport: { width: 1280, height: 800 } })
const admin = await adminCtx.newPage()
await admin.goto(`${BASE}/login?next=/admin/users`)
await admin.getByLabel('이메일').fill(ADMIN)
await admin.getByLabel('비밀번호').fill(ADMIN_PW)
await admin.getByRole('button', { name: '로그인' }).click()
await admin.waitForURL('**/admin/users**')
const row = admin.getByRole('row').filter({ hasText: USER })
await row.waitFor()
await admin.screenshot({ path: `${OUT}03-admin-pending.png` })
await row.getByRole('button', { name: '승인' }).click()
await admin.getByRole('dialog').waitFor()
await admin.screenshot({ path: `${OUT}04-admin-confirm.png` })
await admin.getByRole('dialog').getByRole('button', { name: '확인' }).click()
await admin.getByText('변경했어요.').waitFor()
ok('관리자 승인(확인 모달)', true)

// 4. 로그인 (키보드만)
await page.goto(`${BASE}/login`)
await page.getByLabel('이메일').waitFor()
await page.keyboard.press('Tab')
const first = await page.evaluate(() => document.activeElement?.getAttribute('type'))
await page.keyboard.type(USER)
await page.keyboard.press('Tab')
const second = await page.evaluate(() => document.activeElement?.getAttribute('type'))
await page.keyboard.type(PW)
const ring = await page.evaluate(() => getComputedStyle(document.activeElement).outlineColor)
await page.keyboard.press('Enter')
await page.waitForURL('**/search')
ok('키보드만으로 로그인 (Tab→이메일→Tab→비밀번호→Enter)', first === 'email' && second === 'password', `${first},${second}`)
ok('키보드 포커스 링 표시', ring === 'rgb(47, 91, 234)', ring)
await page.screenshot({ path: `${OUT}05-shell-1280.png` })

// 5. 새로고침 후 유지 (access 쿠키를 지워 refresh 경로도 확인)
await page.reload()
await page.waitForURL('**/search')
ok('새로고침 후 로그인 유지', page.url().endsWith('/search'))
const cookies = await userCtx.cookies()
ok('토큰 쿠키는 HttpOnly', cookies.filter((c) => c.name.endsWith('_token')).every((c) => c.httpOnly))
await userCtx.clearCookies({ name: 'access_token' })
await page.goto(`${BASE}/library`)
await page.waitForURL('**/library')
ok('access 만료(삭제) 후 refresh로 유지', page.url().endsWith('/library'))
const jsSeesToken = await page.evaluate(() => document.cookie.includes('token'))
ok('JS에서 토큰 쿠키 접근 불가', !jsSeesToken)

// 6. 로그아웃
await page.getByRole('button', { name: '사용자 메뉴' }).click()
await page.getByRole('menuitem', { name: '로그아웃' }).click()
await page.waitForURL('**/login')
await page.goto(`${BASE}/search`)
await page.waitForURL('**/login?next=**')
ok('로그아웃 후 보호 화면 → 로그인', true)

// 7. 입력 테두리 대비 (§10.1 --border-input #8590A0, 흰 배경 3.23:1)
const border = await page.getByLabel('이메일').evaluate((el) => getComputedStyle(el).borderTopColor)
ok('입력 테두리 색 = --border-input', border === 'rgb(133, 144, 160)', border)
const lum = (r, g, b) => {
  const f = (c) => ((c /= 255) <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}
const ratio = (1.05) / (lum(133, 144, 160) + 0.05)
ok('입력 테두리 대비 ≥ 3:1', ratio >= 3, ratio.toFixed(2))

// 8. 반응형 스크린샷과 가로 스크롤 없음
const adminState = await adminCtx.storageState() // 로그인 속도 제한(IP 분당 5회)을 피해 세션 재사용
for (const w of [375, 768, 1280]) {
  const guest = await browser.newContext({ viewport: { width: w, height: 800 } })
  const g = await guest.newPage()
  await g.goto(`${BASE}/login`)
  await g.getByLabel('이메일').waitFor()
  ok(`${w}px 로그인 화면 가로 스크롤 없음`, !(await g.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)))
  await g.screenshot({ path: `${OUT}06-login-${w}.png` })
  await guest.close()
  const ctx = await browser.newContext({ viewport: { width: w, height: 800 }, storageState: adminState })
  const p = await ctx.newPage()
  await p.goto(`${BASE}/admin/users?tab=active`)
  await p.getByRole('row').filter({ hasText: USER }).first().waitFor()
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  ok(`${w}px 가로 스크롤 없음 (관리자 화면)`, !overflow)
  await p.screenshot({ path: `${OUT}07-admin-${w}.png`, fullPage: true })
  await ctx.close()
}

ok('브라우저 콘솔 오류 없음', consoleErrors.length === 0, consoleErrors.join(' | '))
await browser.close()
console.log(results.join('\n'))

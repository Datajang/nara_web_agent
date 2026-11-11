// P3b 브라우저 게이트 (SPEC §7.11). 개발 서버: 백엔드 LLM_BACKEND=fake, G2B 키 없음, 첨부 허용 호스트 비움
// (외부 호출 없음). 실행: E2E_ADMIN=... E2E_ADMIN_PW=... node e2e/p3b-flow.mjs
import { chromium } from 'playwright'
import { createRequire } from 'node:module'

const require = createRequire(new URL('../package.json', import.meta.url))
const AXE = process.env.E2E_AXE ?? require.resolve('axe-core/axe.min.js')
const BASE = process.env.E2E_BASE ?? 'http://localhost:5173'
const OUT = process.env.E2E_SHOTS ?? new URL('./shots/', import.meta.url).pathname
const ADMIN = process.env.E2E_ADMIN
const ADMIN_PW = process.env.E2E_ADMIN_PW
const STAMP = Date.now()
const A = `e2e-a-${STAMP}@corp.example`
const B = `e2e-b-${STAMP}@corp.example`
const PW = 'e2e-user-password-1'
const PROFILE = '공공 AI 시스템 구축 팀. 검색·데이터 플랫폼 개발 경험이 많습니다.'
const H = { Origin: BASE }
const results = []
const ok = (name, cond, extra = '') => {
  results.push(`${cond ? 'PASS' : 'FAIL'}  ${name}${extra ? ' — ' + extra : ''}`)
  if (!cond) process.exitCode = 1
}
const noHScroll = (p) => p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)

const browser = await chromium.launch()

// ---------- 준비: 관리자 로그인, 회원 둘 가입 → 메일 인증 → 승인 (API로) ----------
const adminCtx = await browser.newContext()
const admin = adminCtx.request
let r = await admin.post(`${BASE}/api/v1/auth/login`, { headers: H, data: { email: ADMIN, password: ADMIN_PW } })
ok('관리자 로그인', r.ok(), String(r.status()))
for (const email of [A, B]) {
  await admin.post(`${BASE}/api/v1/auth/register`, { headers: H, data: { email, password: PW, display_name: '' } })
  const mails = (await (await admin.get(`${BASE}/api/v1/_dev/mail`)).json()).items
  const token = mails.filter((m) => m.to === email).at(-1).body.match(/token=([\w-]+)/)[1]
  await admin.post(`${BASE}/api/v1/auth/verify-email`, { headers: H, data: { token } })
  const pending = (await (await admin.get(`${BASE}/api/v1/admin/users?status=pending_approval`)).json()).items
  const u = pending.find((x) => x.email === email)
  r = await admin.patch(`${BASE}/api/v1/admin/users/${u.id}`, { headers: H, data: { status: 'active' } })
  ok(`가입·인증·승인 ${email.slice(0, 8)}`, r.ok())
}

async function loginPage(email, viewport = { width: 1280, height: 800 }) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  const errors = []
  page.on('console', (m) => m.type() === 'error' && !m.text().startsWith('Failed to load resource') && errors.push(m.text()))
  page.on('dialog', (d) => {
    errors.push(`dialog:${d.message()}`)
    void d.dismiss()
  })
  await page.goto(`${BASE}/login`)
  await page.getByLabel('이메일').fill(email)
  await page.getByLabel('비밀번호').fill(PW)
  await page.getByRole('button', { name: '로그인' }).click()
  await page.waitForURL('**/search**')
  return { ctx, page, errors }
}

async function axeCheck(page, name) {
  await page.addScriptTag({ path: AXE })
  const res = await page.evaluate(async () => {
    const out = await window.axe.run(document, { resultTypes: ['violations'] })
    return out.violations.filter((v) => v.impact === 'critical').map((v) => v.id)
  })
  ok(`axe critical 0: ${name}`, res.length === 0, res.join(','))
}

// ---------- 회원 A: 프로필 → 검색(URL 복원) → 상세 → 분석 → 내 기록에서 다시 열기 (§7.11-2·4) ----------
const a = await loginPage(A)
await a.page.goto(`${BASE}/settings/profiles`)
await a.page.getByRole('button', { name: '새 프로필' }).click()
await a.page.getByLabel('이름').fill('AI 팀')
await a.page.getByLabel('팀 소개').fill(PROFILE)
await a.page.getByRole('button', { name: '키워드 제안' }).click()
await a.page.getByRole('button', { name: /삭제$/ }).first().waitFor()
ok('키워드 제안으로 칩 채움', (await a.page.getByRole('button', { name: /삭제$/ }).count()) > 0)
await a.page.getByRole('button', { name: '저장' }).click()
await a.page.getByText('기본', { exact: true }).waitFor()
ok('프로필 저장(첫 프로필은 기본)', true)
await axeCheck(a.page, '/settings/profiles')

await a.page.goto(`${BASE}/search?q=시스템&days=30&status=all&sort=deadline_asc`)
await a.page.getByText(/총 \d+건/).waitFor()
await a.page.reload()
await a.page.getByText(/총 \d+건/).waitFor()
const chipKept = await a.page.getByRole('button', { name: '시스템 삭제' }).isVisible()
const sortKept = await a.page.getByLabel('정렬').inputValue()
ok('새로고침 후 URL로 검색 조건 복원 (§7.11-4)', chipKept && sortKept === 'deadline_asc', sortKept)
await a.page.screenshot({ path: `${OUT}p3b-search-1280.png` })
await axeCheck(a.page, '/search')

const firstTitle = a.page.locator('article h3 a').first()
const bidHref = await firstTitle.getAttribute('href')
await firstTitle.click()
await a.page.waitForURL(`**${bidHref}`)
await a.page.getByRole('button', { name: '분석하기' }).click()
await a.page.getByRole('heading', { name: '다음 할 일 제안' }).waitFor({ timeout: 30000 })
const heads = await a.page.locator('section h3').allTextContents()
const order = ['사업 개요', '핵심 요구사항', '평가 기준·배점', '일정', '예산·계약 조건', '리스크·유의사항', '우리 팀 적합도', '다음 할 일 제안']
ok('분석 결과가 §7.5 순서로 표시', JSON.stringify(heads.filter((h) => order.includes(h))) === JSON.stringify(order))
ok('첨부를 못 읽으면 경고 배너', await a.page.getByText('첨부 문서를 읽지 못해 공고 정보만으로 분석했어요.').isVisible())
await a.page.screenshot({ path: `${OUT}p3b-detail-1280.png`, fullPage: true })
await axeCheck(a.page, '/bids/:id')

await a.page.goto(`${BASE}/library?tab=analyses`)
await a.page.locator(`a[href^="${bidHref}?analysis="]`).click()
await a.page.getByRole('heading', { name: '사업 개요' }).waitFor()
ok('내 기록 → 분석 다시 열기 (§7.11-2)', true)
await a.page.goto(`${BASE}/library?tab=runs`)
await a.page.getByRole('button', { name: '열기' }).first().click()
await a.page.getByRole('button', { name: '목록으로' }).waitFor()
ok('검색 기록 스냅샷 열기', (await a.page.locator('article').count()) > 0)
await axeCheck(a.page, '/library')

// 분석 도중 탭을 닫았다가 다시 열기 (§7.11-6)
await a.page.goto(`${BASE}/search?q=데이터&days=30&status=all`)
await a.page.getByText(/총 \d+건/).waitFor()
const second = await a.page.locator('article h3 a').nth(1).getAttribute('href')
const closing = await a.ctx.newPage()
await closing.goto(`${BASE}${second}`)
await closing.getByRole('button', { name: '분석하기' }).click()
await closing.close()
await new Promise((res) => setTimeout(res, 1500))
const reopen = await a.ctx.newPage()
await reopen.goto(`${BASE}${second}`)
await reopen.getByRole('heading', { name: '사업 개요' }).waitFor({ timeout: 10000 })
ok('분석 중 탭을 닫아도 다시 열면 저장된 분석이 바로 보임 (§7.11-6)', true)
await reopen.close()

// 맞춤 추천
await a.page.goto(`${BASE}/recommend`)
await a.page.getByRole('button', { name: '추천 받기' }).click()
await a.page.locator('article').first().waitFor({ timeout: 60000 })
ok('추천 카드에 점수 배지', (await a.page.getByText(/\d+점 · (높음|보통|낮음)/).count()) > 0)
await a.page.screenshot({ path: `${OUT}p3b-recommend-1280.png` })
await axeCheck(a.page, '/recommend')

// 어시스턴트
await a.page.goto(`${BASE}/assistant`)
await a.page.getByLabel('메시지').fill('AI 공고 찾아줘')
await a.page.keyboard.press('Enter')
await a.page.waitForURL('**/assistant/*')
await a.page.locator('article').first().waitFor({ timeout: 30000 })
const reply = await a.page.locator('.whitespace-pre-wrap').last().textContent()
ok('어시스턴트: 토큰 스트리밍 + 인라인 카드', /b\d+/.test(reply ?? ''), reply ?? '')
await a.page.screenshot({ path: `${OUT}p3b-assistant-1280.png` })
await axeCheck(a.page, '/assistant')

// XSS: 공고 제목의 HTML이 실행되지 않고 글자로 (§7.11-5). 응답을 가로채 제목만 바꾼다(DB는 건드리지 않음)
await a.page.route('**/api/v1/bids/search', async (route) => {
  const res = await route.fetch()
  const body = await res.json()
  if (body.items[0]) body.items[0].title = '<img src=x onerror=alert(1)>XSS 시험'
  await route.fulfill({ response: res, json: body })
})
await a.page.goto(`${BASE}/search?q=시스템&days=30&status=all`)
await a.page.getByText('<img src=x onerror=alert(1)>XSS 시험').waitFor()
ok('제목의 <img onerror>가 글자로 보이고 실행되지 않음 (§7.11-5)', (await a.page.locator('article img').count()) === 0 && !a.errors.some((e) => e.startsWith('dialog')))
await a.page.unroute('**/api/v1/bids/search')

// 403 (§7.11-9)
await a.page.goto(`${BASE}/admin/usage`)
const forbidden = await a.page.getByText('접근 권한이 없어요').waitFor({ timeout: 5000 }).then(() => true, () => false)
ok('일반 회원의 /admin/* → 403 화면 (§7.11-9)', forbidden && a.page.url().endsWith('/admin/usage'))

// ---------- 회원 B: 같은 프로필 텍스트로 같은 공고 → 즉시, LLM 0회 (§7.11-3) ----------
const b = await loginPage(B)
await b.page.request.post(`${BASE}/api/v1/profiles`, { headers: H, data: { name: 'B 팀', description: PROFILE, keywords: [], is_default: true } })
await b.page.goto(`${BASE}${bidHref}`)
const sseResp = b.page.waitForResponse((res) => res.url().endsWith('/analyze'))
const t0 = Date.now()
await b.page.getByRole('button', { name: '분석하기' }).click()
const body = await (await sseResp).text()
await b.page.getByText('저장된 분석을 재사용했어요.').waitFor()
const done = body.split('\n\n').filter((x) => x.startsWith('data: ')).map((x) => JSON.parse(x.slice(6))).find((e) => e.type === 'done')
ok('B: LLM 호출 0회, 캐시 전부 적중 (§7.11-3)', done?.usage.llm_calls === 0 && Object.values(done.usage.cache).every(Boolean), JSON.stringify(done?.usage))
ok('B: 결과가 즉시 (2초 이내)', Date.now() - t0 < 2000, `${Date.now() - t0}ms`)

// ---------- 375·768·1280px: 검색 → 카드 → 상세, 가로 스크롤 없음 (§7.11-8, §10.10-6) ----------
for (const width of [375, 768, 1280]) {
  const p = await b.ctx.newPage()
  await p.setViewportSize({ width, height: 800 })
  for (const [path, name] of [
    ['/search?q=시스템&days=30&status=all', 'search'],
    [bidHref, 'detail'],
    ['/recommend', 'recommend'],
    ['/assistant', 'assistant'],
    ['/library?tab=bookmarks', 'library'],
    ['/settings/profiles', 'settings'],
  ]) {
    await p.goto(`${BASE}${path}`)
    await p.waitForLoadState('networkidle')
    ok(`${width}px ${name} 가로 스크롤 없음`, await noHScroll(p))
    await p.screenshot({ path: `${OUT}p3b-${name}-${width}.png`, fullPage: true })
  }
  if (width === 375) {
    await p.goto(`${BASE}/search?q=시스템&days=30&status=all`)
    await p.locator('article h3 a').first().click()
    await p.waitForURL('**/bids/**')
    ok('375px 검색 → 카드 → 상세 이동', true)
  }
  await p.close()
}

// ---------- 관리자 화면 ----------
const adminPage = await adminCtx.newPage()
await adminPage.setViewportSize({ width: 1280, height: 800 })
await adminPage.goto(`${BASE}/admin/usage`)
await adminPage.getByText('G2B 호출').waitFor()
ok('관리자 사용량 화면', await adminPage.locator('canvas').count() > 0)
await adminPage.screenshot({ path: `${OUT}p3b-admin-usage.png`, fullPage: true })
await axeCheck(adminPage, '/admin/usage')
await adminPage.goto(`${BASE}/admin/collector`)
await adminPage.getByText('수집 범위').waitFor()
ok('관리자 수집기 화면(범위 표시)', await adminPage.getByText('일반공고').first().isVisible())
await adminPage.screenshot({ path: `${OUT}p3b-admin-collector.png`, fullPage: true })

ok('브라우저 콘솔 오류 없음', [...a.errors, ...b.errors].length === 0, [...a.errors, ...b.errors].join(' | '))
await browser.close()
console.log(results.join('\n'))
console.log(`E2E_USERS ${A} ${B}`)

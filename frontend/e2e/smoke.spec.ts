// main 병합 스모크 (SPEC §12.8, §7.11-2 축약, §13 P6): 로그인 → 관심 키워드 → 관심 공고 홈 → 팀 만들기
// → 검색 → 상세 → 분석(가짜 LLM) → 내 기록 → 다시 열기.
// 데이터: backend `python -m scripts.seed_e2e`. 외부 호출 없음(가짜 LLM, 수집 범위가 검색 창을 덮음).
import { expect, test } from '@playwright/test'
import { copy } from '../src/copy'

const ADMIN = process.env.E2E_ADMIN ?? 'e2e-admin@corp.example'
const ADMIN_PW = process.env.E2E_ADMIN_PW ?? 'e2e-admin-password-1'

test('로그인부터 분석 기록 다시 열기까지', async ({ page }) => {
  const errors: string[] = []
  page.on('console', (m) => {
    if (m.type() === 'error' && !m.text().startsWith('Failed to load resource')) errors.push(m.text())
  })

  await page.goto('/login')
  await page.getByLabel('이메일').fill(ADMIN)
  await page.getByLabel('비밀번호').fill(ADMIN_PW)
  await page.getByRole('button', { name: '로그인' }).click()

  // P6: 키워드가 3개 미만이면 키워드 설정으로, 정하면 관심 공고 홈
  await page.waitForURL(/\/(onboarding)?$/)
  await page.goto('/onboarding')
  const kw = page.getByLabel(copy.onboarding.personalLabel)
  for (const k of ['클라우드', '데이터', '플랫폼']) {
    await kw.fill(k)
    await kw.press('Enter')
  }
  await page.getByRole('button', { name: copy.onboarding.save }).click()
  await page.waitForURL((u) => u.pathname === '/')
  await expect(page.locator('[data-matched]').first()).toBeVisible()

  // P6: 팀 만들기 → 초대 링크 (이미 팀이 있으면 그대로)
  await page.goto('/settings/team')
  const createBtn = page.getByRole('button', { name: copy.team.create })
  const invite = page.getByText(copy.team.inviteLink, { exact: true })
  await expect(createBtn.or(invite)).toBeVisible() // 화면이 다 뜬 뒤에 판단
  if (await createBtn.isVisible()) {
    await page.getByLabel(copy.team.nameLabel).fill('E2E 팀')
    await createBtn.click()
  }
  await expect(invite).toBeVisible()

  // 분석에는 프로필이 필요하다
  await page.goto('/settings/profiles')
  await page.getByRole('button', { name: '새 프로필' }).click()
  await page.getByLabel('이름').fill('E2E 팀')
  await page.getByLabel('팀 소개').fill('공공 클라우드 전환과 데이터 플랫폼 구축 경험이 있는 팀입니다.')
  await page.getByRole('button', { name: '저장' }).click()
  await page.getByText('기본', { exact: true }).waitFor()

  await page.goto('/search?q=클라우드&days=7')
  await expect(page.getByText(/총 \d+건/)).toBeVisible()
  const first = page.locator('article h3 a').first()
  await expect(first).toContainText('클라우드')
  const href = await first.getAttribute('href')
  await first.click()
  await page.waitForURL(`**${href}`)

  await page.getByRole('button', { name: copy.detail.analyzeSubmit }).click()
  await expect(page.getByRole('heading', { name: copy.analysis.nextActions })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole('heading', { name: copy.analysis.overview })).toBeVisible()

  await page.goto('/library?tab=analyses')
  await page.locator(`a[href^="${href}?analysis="]`).first().click()
  await expect(page.getByRole('heading', { name: copy.analysis.overview })).toBeVisible()

  expect(errors).toEqual([])
})

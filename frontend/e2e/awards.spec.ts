// P9·P10 시나리오 (SPEC §15.11): 회사 설정(사업자번호 → 이름 자동) → 우리 수주 현황 → 업체 검색 → 낙찰 목록
// → 우리 회사와 비교(강점·약점·판정 표) → 경쟁사 레이더 → 관심 경쟁사 추가·빼기.
// 데이터: backend `python -m scripts.seed_e2e`(낙찰 5건, 수집 범위 400일). 외부 호출 없음.
// 화면 캡처는 test-results/p9-*.png, p10-*.png (git 제외).
import { expect, test } from '@playwright/test'
import { copy } from '../src/copy'

const ADMIN = process.env.E2E_ADMIN ?? 'e2e-admin@corp.example'
const ADMIN_PW = process.env.E2E_ADMIN_PW ?? 'e2e-admin-password-1'
const OUR_NAME = '(주)이투이예시' // scripts/seed_e2e.py E2E_OUR_NAME

test('회사 설정부터 업체 검색 낙찰 목록까지', async ({ page }) => {
  const errors: string[] = []
  page.on('console', (m) => {
    if (m.type() === 'error' && !m.text().startsWith('Failed to load resource')) errors.push(m.text())
  })
  await page.setViewportSize({ width: 1280, height: 900 })

  await page.goto('/login')
  await page.getByLabel('이메일').fill(ADMIN)
  await page.getByLabel('비밀번호').fill(ADMIN_PW)
  await page.getByRole('button', { name: '로그인' }).click()
  await page.waitForURL((u) => u.pathname !== '/login')

  // 회사 설정: 사업자번호로 이름 찾기 → 저장
  await page.goto('/company')
  await page.waitForURL('**/admin/company')
  await page.getByLabel(copy.company.bizno).fill('123-45-67890')
  await page.getByLabel(copy.company.name).fill('')
  await page.getByRole('button', { name: copy.company.lookup }).click()
  await expect(page.getByLabel(copy.company.name)).toHaveValue(OUR_NAME)
  await page.getByLabel(copy.company.fields).fill('데이터: 데이터\nAI: AI')
  await page.getByRole('button', { name: copy.company.save }).click()
  await expect(page.getByText(/저장했어요|다시 분류/)).toBeVisible()
  await page.screenshot({ path: 'test-results/p9-company.png', fullPage: true })

  // 우리 수주 현황: 사이드바 메뉴로
  await page.getByRole('link', { name: copy.nav.myAwards }).click()
  await page.waitForURL('**/my-awards')
  await expect(page.getByText(OUR_NAME).first()).toBeVisible()
  await expect(page.getByText(copy.awards.basis).first()).toBeVisible()
  await expect(page.locator('[data-award-table] tbody tr')).toHaveCount(3)
  await expect(page.getByText('E2E 데이터 정비 사업')).toBeVisible()
  await page.screenshot({ path: 'test-results/p9-my-awards.png', fullPage: true })

  // 업체 검색 → 고르기 → 목록
  await page.getByRole('link', { name: copy.nav.companies }).click()
  await page.getByLabel(copy.companies.searchLabel).fill('가온')
  await page.getByRole('button', { name: copy.companies.submit }).click()
  await page.locator('[data-company-hit]').first().click()
  await expect(page).toHaveURL(/bizno=2345678901/)
  await expect(page.locator('[data-award-table] tbody tr')).toHaveCount(2)
  await expect(page.getByText('E2E 클라우드 전환 사업')).toBeVisible()
  await page.screenshot({ path: 'test-results/p9-companies.png', fullPage: true })

  // 새로고침해도 같은 업체가 열린다(URL 동기화)
  await page.reload()
  await expect(page.getByText('E2E 데이터 품질 진단')).toBeVisible()

  // P10: 우리 회사와 비교 — 맨 위 강점·약점, 판정 배지는 글자와 함께
  await page.getByRole('link', { name: copy.competitors.compareWithUs }).click()
  await page.waitForURL('**/competitors/2345678901')
  await expect(page.getByRole('heading', { name: copy.competitors.strengths })).toBeVisible()
  await expect(page.getByRole('heading', { name: copy.competitors.weaknesses })).toBeVisible()
  const countRow = page.locator('[data-row="count"]')
  await expect(countRow).toContainText(copy.competitors.verdicts.up) // 시드: 우리 3건 vs 가온 2건 → +33%
  await page.screenshot({ path: 'test-results/p10-compare.png', fullPage: true })

  // 경쟁사 레이더 → 관심 경쟁사 추가 → 목록에서 빼기(다시 돌려도 같은 상태)
  await page.getByRole('link', { name: copy.nav.competitors }).click()
  await page.waitForURL('**/competitors')
  const rival = page.locator('[data-candidates] tbody tr', { hasText: '가온데이터시스템(주)' })
  await expect(rival).toBeVisible()
  await rival.getByRole('button', { name: copy.competitors.watchAdd }).click()
  await expect(page.locator('[data-watch-list]')).toContainText('가온데이터시스템(주)')
  await page.screenshot({ path: 'test-results/p10-radar.png', fullPage: true })
  await page.locator('[data-watch-list]').getByRole('button', { name: copy.competitors.watchRemove }).click()
  await expect(page.getByText(copy.competitors.noWatched)).toBeVisible()

  expect(errors).toEqual([])
})

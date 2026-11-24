// P9~P11 시나리오 (SPEC §15.11): 회사 설정(사업자번호 → 이름 자동) → 우리 수주 현황 → 업체 검색 → 낙찰 목록
// → 우리 회사와 비교(강점·약점·판정 표, 공동수급 파트너, AI 해설) → 경쟁사 레이더 → 관심 경쟁사 추가·빼기
// → 공고 상세 '경쟁 구도' 탭. P12: 우리 수주 현황 '투찰 결과' 탭(낙찰·탈락)과 상세.
// 데이터: backend `python -m scripts.seed_e2e`(낙찰 5건·개찰 결과 캐시·공동수급 1건). 외부 호출 없음, LLM은 가짜.
// 화면 캡처는 test-results/p9-*.png, p10-*.png, p11-*.png, p12-*.png (git 제외).
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
  await page.getByLabel('이메일', { exact: true }).fill(ADMIN)
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

  // P12: 투찰 결과 탭 — 낙찰 3, 탈락 2(2위 1건, 순위 없이 사유만 1건) → 상세에 참가 업체 전체·비교 링크
  await page.getByRole('tab', { name: copy.myBids.tabBids }).click()
  await expect(page).toHaveURL(/tab=bids/)
  await expect(page.locator('[data-my-bids] tbody tr')).toHaveCount(5)
  await expect(page.locator('[data-my-bid="R26BKE2A00004"] [data-rank]')).toHaveText(copy.myBids.rank(2, 2))
  const dq = page.locator('[data-my-bid="R26BKE2A00005"]')
  await expect(dq.locator('[data-rank]')).toHaveText(`${copy.myBids.noRank} · 낙찰하한선 미달`)
  await page.getByText(copy.myBids.filterLost(2)).click()
  await expect(page).toHaveURL(/result=lost/)
  await expect(page.locator('[data-my-bids] tbody tr')).toHaveCount(2)
  await page.screenshot({ path: 'test-results/p12-my-bids.png', fullPage: true })
  await dq.getByRole('link', { name: 'E2E 데이터 품질 진단' }).click()
  await page.waitForURL('**/my-awards/bids/R26BKE2A00005/**')
  await expect(page.locator('[data-our-result]')).toContainText('낙찰하한선 미달')
  const prow = page.locator('[data-participants] tbody tr')
  await expect(prow).toHaveCount(2)
  await expect(prow.first().getByRole('link', { name: copy.myBids.compare })).toHaveAttribute('href', '/competitors/2345678901')
  await page.screenshot({ path: 'test-results/p12-my-bid-detail.png', fullPage: true })

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

  // P11: 공동수급 파트너(계약정보)와 AI 해설(숫자 검증을 통과한 글만)
  await expect(page.locator('[data-joint-side="us"]')).toContainText('E2E 파트너(주)')
  const ai = page.locator('[data-ai-explain]')
  await ai.getByRole('button', { name: copy.competitors.aiStart }).click()
  await expect(ai.locator('[data-ai-text]')).toBeVisible({ timeout: 30_000 })
  await expect(ai).toContainText(copy.competitors.aiBadge)
  await page.screenshot({ path: 'test-results/p11-compare-ai.png', fullPage: true })

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

  // P11: 공고 상세 '경쟁 구도' 탭 — 같은 수요기관의 비슷한 과거 낙찰, 분포, 참가 업체 점수, 우리 이력
  await page.goto('/search?q=플랫폼&days=7')
  const bidLink = page.locator('article h3 a', { hasText: 'E2E AI 데이터 플랫폼 고도화' })
  await bidLink.click()
  await page.waitForURL('**/bids/*')
  await page.getByRole('tab', { name: copy.competition.tabCompetition }).click()
  await expect(page).toHaveURL(/tab=competition/)
  await expect(page.locator('[data-similar]')).toContainText('E2E AI 분석 플랫폼 구축')
  await expect(page.locator('[data-us-history]')).toContainText(copy.competition.usTitle)
  const first = page.locator('[data-similar] [data-award]').first()
  await first.getByRole('button', { name: new RegExp(copy.competition.showParticipants) }).click()
  await expect(first.locator('[data-participants] tbody tr')).toHaveCount(2)
  await page.screenshot({ path: 'test-results/p11-competition.png', fullPage: true })

  expect(errors).toEqual([])
})

// P10 화면 (SPEC §15.7): 경쟁사 레이더, 우리 회사와 경쟁사 비교, 업체 검색의 비교·관심 버튼.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { copy } from '@/copy'
import { json, mockApi, mountAt, settle, text, type Mounted } from './helpers'

let m: Mounted | null = null
beforeEach(() => {
  document.body.innerHTML = ''
})
afterEach(() => {
  m?.wrapper.unmount()
  m = null
  vi.unstubAllGlobals()
})

const PERIOD = { from: '2021-11-11', to: '2026-11-10', counted_from: '2021-11-11', counted_to: '2026-11-10', collecting: false }
const US = { bizno: '1234567890', name: '(주)예시컴퍼니' }
const THEM = { bizno: '2345678901', name: '가온데이터시스템(주)' }

function summary(over: Record<string, unknown> = {}) {
  return {
    ...US,
    is_us: true,
    period: PERIOD,
    count: 7,
    amount_sum: 700_000_000,
    amount_avg: 100_000_000,
    org_count: 3,
    g2b_rate_median: null,
    ratio_median: null,
    ratio_known: 0,
    joint_count: 0,
    first_at: null,
    last_at: null,
    by_year: [],
    by_org: [{ dminstt_cd: '1111111', dminstt_name: '행정안전부', count: 4, amount_sum: 400_000_000 }],
    by_field: [],
    fields: ['AI', '데이터 정비'],
    ...over,
  }
}

const v = (key: string, label: string, us: number | null, them: number | null, verdict: string, rule: string, small = false) => ({
  key,
  label,
  us,
  them,
  verdict,
  rule,
  small_sample: small,
})

const COMPARE = {
  period: PERIOD,
  note: '두 회사 모두 수집 완료된 기간',
  us: US,
  them: THEM,
  verdicts: [
    v('count', '낙찰 건수', 7, 12, 'down', 'ratio_20'),
    v('amount_sum', '낙찰금액 합계', 700_000_000, 2_400_000_000, 'down', 'ratio_20'),
    v('amount_avg', '건당 평균 낙찰금액', 100_000_000, 200_000_000, 'down', 'ratio_20'),
    v('org_count', '낙찰한 수요기관 수', 3, 3, 'same', 'ratio_20'),
    v('field:AI', 'AI', 4, 1, 'up', 'field_2x'),
    v('field:데이터 정비', '데이터 정비', 1, 1, 'info', 'field_2x', true),
    v('head_to_head', '직접 맞붙은 공고', 2, 1, 'up', 'head_to_head', true),
    v('g2b_rate_median', '낙찰률(G2B) 중앙값', 87.5, null, 'info', 'info'),
  ],
  strengths: ['field:AI', 'head_to_head'],
  weaknesses: ['amount_sum', 'amount_avg', 'count'],
  coverage: { complete_from: '2021-11-11', collecting: false },
  head_to_head: { matched: 3, us_wins: 2, them_wins: 1 },
  by_year: [
    { year: 2025, us: 3, them: 5, collecting: false },
    { year: 2026, us: 4, them: 7, collecting: false },
  ],
  shared_orgs: [{ dminstt_cd: '1111111', dminstt_name: '행정안전부', us: 4, them: 2 }],
  watched: false,
}

describe('경쟁사 레이더 (/competitors)', () => {
  it('겹침도 순 후보, 필터는 URL에, 관심 경쟁사 추가', async () => {
    let watched = false
    const api = mockApi({
      'GET /api/v1/awards/summary': json(summary()),
      'GET /api/v1/competitors/candidates': json({
        period: PERIOD,
        us: US,
        our_count: 7,
        items: [
          { ...THEM, overlap: 66.7, org_overlap: 0.6667, field_overlap: 0.6667, award_count: 12, last_award_at: '2026-10-01T00:00:00Z', watched: false },
        ],
      }),
      'GET /api/v1/competitors/watch': () =>
        json({ items: watched ? [{ ...THEM, added_at: '2026-11-16T00:00:00Z', award_count: 12, last_award_at: null }] : [] }),
      'PUT /api/v1/competitors/watch/2345678901': () => {
        watched = true
        return json({ items: [] })
      },
    })
    m = await mountAt('/competitors')
    const t = text(m.wrapper)
    for (const s of [copy.competitors.ourSummary(US.name, 7), THEM.name, '66.7', copy.competitors.overlapDetail('66.7', '66.7'), copy.competitors.noWatched])
      expect(t).toContain(s)
    expect(m.wrapper.get(`a[href="/competitors/${THEM.bizno}"]`).text()).toBe(THEM.name)

    await m.wrapper.get('[data-candidates] [data-watch]').trigger('click')
    await settle()
    expect(api.calls.some((c) => c.method === 'PUT')).toBe(true)
    expect(m.wrapper.get('[data-watch-list]').text()).toContain(THEM.name)

    const select = m.wrapper.findAll('select')[0]!
    await select.setValue('AI')
    await settle()
    expect(m.router.currentRoute.value.query.field).toBe('AI')
    const last = api.calls.filter((c) => c.url.startsWith('/api/v1/competitors/candidates')).slice(-1)[0]!
    expect(last.url).toContain('field=AI')
  })
})

describe('우리 회사와 경쟁사 비교 (/competitors/:bizno)', () => {
  it('강점·약점 카드와 판정 표, 배지는 글자와 함께', async () => {
    mockApi({
      'GET /api/v1/compare/2345678901': json(COMPARE),
      'GET /api/v1/companies/2345678901': json(summary({ ...THEM, is_us: false })),
      'GET /api/v1/awards': json({ period: PERIOD, total: 0, next_cursor: null, items: [] }),
      'GET /api/v1/competitors/watch': json({ items: [] }),
    })
    m = await mountAt(`/competitors/${THEM.bizno}`)
    const strengths = m.wrapper.get('[data-strengths]').text()
    const weaknesses = m.wrapper.get('[data-weaknesses]').text()
    expect(strengths).toContain('AI')
    expect(strengths).toContain(copy.competitors.verdicts.up)
    expect(strengths).toContain(copy.competitors.smallSample) // 맞대결 3건 < 5
    expect(weaknesses).toContain('낙찰금액 합계')
    expect(weaknesses).toContain(copy.competitors.cardLine('7억', '24억'))
    // 약점 카드는 서버 순서(|차이| 큰 순) 그대로
    expect(weaknesses.indexOf('낙찰금액 합계')).toBeLessThan(weaknesses.indexOf('낙찰 건수'))

    const row = (k: string) => m!.wrapper.get(`[data-row="${k}"]`).text()
    expect(row('count')).toContain(copy.competitors.verdicts.down)
    expect(row('org_count')).toContain(copy.competitors.verdicts.same)
    expect(row('field:데이터 정비')).toContain(copy.competitors.verdicts.info)
    expect(row('field:데이터 정비')).toContain(copy.competitors.smallSample)
    expect(row('head_to_head')).toContain(copy.competitors.h2hRule(3))
    expect(row('g2b_rate_median')).toContain('87.5%')
    expect(row('g2b_rate_median')).toContain(copy.competitors.noValue)
    // 배지에는 항상 글자가 있다(색만으로 구분하지 않음)
    for (const b of m.wrapper.findAll('[data-verdict]')) expect(b.text().length).toBeGreaterThan(0)

    const t = text(m.wrapper)
    for (const s of [
      copy.competitors.periodNote('2021-11-11', '2026-11-10'),
      copy.competitors.legendUs(US.name),
      copy.competitors.legendThem(THEM.name),
      '행정안전부',
      copy.competitors.jointPending,
      copy.competitors.aiPending,
      copy.awards.internalOnly,
    ])
      expect(t).toContain(s)
    expect(m.wrapper.get('[data-pair="2026"]').text()).toContain(copy.awards.countUnit(7))
  })

  it('회사가 설정되지 않았으면 안내', async () => {
    mockApi({
      'GET /api/v1/compare/2345678901': json({ error: { code: 'not_configured', message: '', details: [] } }, 404),
      'GET /api/v1/companies/2345678901': json(summary({ ...THEM, is_us: false })),
      'GET /api/v1/competitors/watch': json({ items: [] }),
    })
    m = await mountAt(`/competitors/${THEM.bizno}`)
    expect(text(m.wrapper)).toContain(copy.awards.notConfiguredBody)
  })
})

describe('업체 검색의 비교·관심 버튼', () => {
  it('다른 업체면 비교 링크와 관심 버튼, 우리 회사면 숨김', async () => {
    mockApi({
      'GET /api/v1/companies/2345678901': json(summary({ ...THEM, is_us: false })),
      'GET /api/v1/companies/1234567890': json(summary()),
      'GET /api/v1/awards': json({ period: PERIOD, total: 0, next_cursor: null, items: [] }),
      'GET /api/v1/competitors/watch': json({ items: [{ ...THEM, added_at: '2026-11-16T00:00:00Z', award_count: 1, last_award_at: null }] }),
    })
    m = await mountAt(`/companies?bizno=${THEM.bizno}`)
    expect(m.wrapper.get('[data-compare-link]').attributes('href')).toBe(`/competitors/${THEM.bizno}`)
    expect(m.wrapper.get('[data-watch]').attributes('aria-pressed')).toBe('true')
    await m.router.replace(`/companies?bizno=${US.bizno}`)
    await settle()
    expect(m.wrapper.find('[data-compare-link]').exists()).toBe(false)
  })
})

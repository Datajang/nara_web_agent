// P11 화면 (SPEC §15.7·§15.8): 공고 상세 '경쟁 구도' 탭, 비교 화면의 AI 해설·공동수급 파트너.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { copy } from '@/copy'
import { COMPARE } from './compareFixture'
import { card, json, mockApi, mountAt, profile, settle, sse, text, type Mounted } from './helpers'

let m: Mounted | null = null
beforeEach(() => {
  document.body.innerHTML = ''
})
afterEach(() => {
  m?.wrapper.unmount()
  m = null
  vi.unstubAllGlobals()
})

const PERIOD = COMPARE.period
const DETAIL = { ...card(), prespec_reg_no: null, related_bid_id: null, files: [], summary: null, my_analysis_id: null }
const US = '1234567890'
const p = (rank: number, bizno: string, name: string, total: number, winner = false) => ({
  rank,
  bizno,
  name,
  bid_amount: 90_000_000,
  bid_rate: null,
  tech_score: 70.5,
  price_score: total - 70.5,
  total_score: total,
  is_winner: winner,
  is_us: bizno === US,
})
const award = (no: string, participants: unknown) => ({
  bid_ntce_no: no,
  bid_ntce_ord: '000',
  title: `${no} 데이터 정비 사업`,
  bizno: '2345678901',
  winner_name: '가온데이터시스템(주)',
  award_amount: 90_000_000,
  g2b_award_rate: 87.5,
  award_ratio: null,
  participant_count: 2,
  registered_at: '2026-10-01T00:00:00Z',
  is_joint: false,
  bid_id: null,
  similarity: 0.8,
  participants,
  us_participated: Array.isArray(participants) && participants.some((x: { is_us: boolean }) => x.is_us),
})
const COMPETITION = {
  bid_id: 'b101',
  org: { code: '1111111', name: '행정안전부' },
  period: PERIOD,
  this_award: null,
  similar: [
    award('R26BK00000001', [p(1, '2345678901', '가온데이터시스템(주)', 90.5, true), p(2, US, '(주)예시컴퍼니', 85.25)]),
    award('R26BK00000002', null),
  ],
  similar_total: 7,
  distribution: { g2b_rate: { n: 6, min: 85.1, median: 87.75, max: 92.8 }, award_ratio: null, basis: 7 },
  participants_status: { requested: 8, loaded: 6, fetched_now: 6, partial: true, failed: false, budget_exhausted: false },
  us: { bizno: US, name: '(주)예시컴퍼니', org_awards: 4, participated: 3, won: 1 },
}

describe("공고 상세 '경쟁 구도' 탭", () => {
  it('탭을 열 때만 불러오고, 분포·일부만 안내·참가 업체 점수·우리 이력을 보여 준다', async () => {
    const api = mockApi({
      'GET /api/v1/bids/b101': json(DETAIL),
      'GET /api/v1/profiles': json({ items: [profile()] }),
      'GET /api/v1/bids/b101/competition': json(COMPETITION),
    })
    m = await mountAt('/bids/b101')
    expect(api.calls.some((c) => c.url.includes('/competition'))).toBe(false) // 공고 정보 탭에서는 안 부름
    const tab = m.wrapper.findAll('[role="tab"]').find((t) => t.text() === copy.competition.tabCompetition)!
    await tab.trigger('mousedown', { button: 0 })
    await settle()
    expect(m.router.currentRoute.value.query.tab).toBe('competition')
    expect(api.calls.filter((c) => c.url.includes('/competition'))).toHaveLength(1)

    const t = text(m.wrapper)
    for (const s of [
      copy.competition.org('행정안전부'),
      copy.competition.partial(6, 8),
      copy.competition.usLine(4, 3, 1),
      copy.competition.similarCount(2, 7),
      copy.competition.notLoaded, // 두 번째 낙찰은 아직 안 불러옴
      copy.awards.basis,
      copy.awards.internalOnly,
    ])
      expect(t).toContain(s)
    const spread = m.wrapper.get('[data-spread="g2b_rate"]').text()
    for (const s of ['85.1%', '87.8%', '92.8%', copy.competition.spreadCount(6)]) expect(spread).toContain(s)
    expect(m.wrapper.get('[data-spread="award_ratio"]').text()).toContain(copy.competition.noSpread)

    // 참가 업체 점수는 펼쳐서 본다. 우리 행·낙찰 행은 글자 배지로
    const first = m.wrapper.get('[data-award="R26BK00000001"]')
    expect(first.text()).toContain(copy.competition.usParticipated)
    await first.get('button[aria-expanded]').trigger('click')
    const rows = first.findAll('[data-participants] tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.text()).toContain(copy.competition.winner)
    expect(rows[1]!.attributes('data-us')).toBe('true')
    expect(rows[1]!.text()).toContain('85.3') // 총점
  })

  it('새로고침해도 탭이 유지되고 공고 정보 탭으로 돌아가면 쿼리가 빠진다', async () => {
    mockApi({
      'GET /api/v1/bids/b101': json(DETAIL),
      'GET /api/v1/profiles': json({ items: [profile()] }),
      'GET /api/v1/bids/b101/competition': json({ ...COMPETITION, us: null, similar: [], similar_total: 0 }),
    })
    m = await mountAt('/bids/b101?tab=competition')
    const t = text(m.wrapper)
    expect(t).toContain(copy.competition.noSimilar)
    expect(t).toContain(copy.competition.usNotConfigured)
    const info = m.wrapper.findAll('[role="tab"]').find((x) => x.text() === copy.competition.tabInfo)!
    await info.trigger('mousedown', { button: 0 })
    await settle()
    expect(m.router.currentRoute.value.query.tab).toBeUndefined()
    expect(text(m.wrapper)).toContain(copy.detail.files)
  })
})

function compareRoutes(extra: Record<string, unknown> = {}) {
  return {
    'GET /api/v1/compare/2345678901': json({ ...COMPARE, ...extra }),
    'GET /api/v1/companies/2345678901': json({
      bizno: '2345678901',
      name: '가온데이터시스템(주)',
      is_us: false,
      period: PERIOD,
      count: 12,
      amount_sum: 0,
      amount_avg: 0,
      org_count: 0,
      g2b_rate_median: null,
      ratio_median: null,
      ratio_known: 0,
      joint_count: 0,
      first_at: null,
      last_at: null,
      by_year: [],
      by_org: [],
      by_field: [],
      fields: [],
    }),
    'GET /api/v1/awards': json({ period: PERIOD, total: 0, next_cursor: null, items: [] }),
    'GET /api/v1/competitors/watch': json({ items: [] }),
  }
}

describe('비교 화면의 AI 해설·공동수급 파트너', () => {
  it('AI 해설은 누를 때 만들고 AI 표시와 함께, 검증 실패면 숨긴다', async () => {
    let verified = true
    const api = mockApi({
      ...compareRoutes(),
      'POST /api/v1/compare/2345678901/explain': () =>
        sse([
          { type: 'status', stage: 'explain', message: '' },
          verified
            ? { type: 'explain', verified: true, explanation: { summary: '두 회사를 비교했어요.', points: ['낙찰 건수 7건 대 12건'] } }
            : { type: 'explain', verified: false, explanation: null },
          { type: 'done', usage: { llm_calls: 1, g2b_calls: 0, cache: {} } },
        ]),
    })
    m = await mountAt('/competitors/2345678901')
    expect(api.calls.some((c) => c.url.endsWith('/explain'))).toBe(false)
    const section = () => m!.wrapper.get('[data-ai-explain]')
    expect(section().text()).toContain(copy.competitors.aiBadge)
    await section().get('button').trigger('click')
    await settle()
    expect(section().get('[data-ai-text]').text()).toContain('낙찰 건수 7건 대 12건')

    verified = false
    await section().get('button').trigger('click')
    await settle()
    expect(section().find('[data-ai-text]').exists()).toBe(false)
    expect(section().get('[data-ai-dropped]').text()).toBe(copy.competitors.aiDropped)
  })

  it('공동수급 파트너: 수집 전이면 수집 중, 수집 뒤엔 두 회사 파트너', async () => {
    mockApi(
      compareRoutes({
        joint: {
          collected: true,
          us: [{ bizno: '3178123292', name: '파트너A', count: 2 }],
          them: [],
        },
      }),
    )
    m = await mountAt('/competitors/2345678901')
    const us = m.wrapper.get('[data-joint-side="us"]').text()
    expect(us).toContain('파트너A')
    expect(us).toContain(copy.competitors.jointCount(2))
    expect(m.wrapper.get('[data-joint-side="them"]').text()).toContain(copy.competitors.jointNone)
    expect(m.wrapper.get('[data-joint-side="us"] a').attributes('href')).toBe('/companies?bizno=3178123292')
  })
})

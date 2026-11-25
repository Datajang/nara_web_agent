// P12 화면: 우리 수주 현황의 '투찰 결과' 탭(낙찰·탈락)과 투찰 결과 상세.
// 순위가 없으면 추정하지 않고 사유(비고)를 보여 준다 (docs/decisions/2026-11-17-p12a-opening-ranks.md).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { myBidsExportFilename, rankText, type MyBid } from '@/api/mybids'
import { copy } from '@/copy'
import { formatMoney, formatPct } from '@/utils/format'
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

const US = '1234567890'
const THEM = '2345678901'
const PERIOD = { from: '2021-11-11', to: '2026-11-10', counted_from: '2024-04-01', counted_to: '2026-11-10', collecting: true }
const SUMMARY = {
  bizno: US,
  name: '(주)예시컴퍼니',
  is_us: true,
  period: PERIOD,
  count: 1,
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
}

function bid(no: string, over: Partial<MyBid> = {}): MyBid {
  return {
    bid_ntce_no: no,
    bid_ntce_ord: '000',
    bid_clsfc_no: '0',
    rbid_no: '000',
    title: `${no} 데이터 정비 용역`,
    dminstt_name: '행정안전부',
    registered_at: '2026-11-01T00:00:00Z',
    opened_at: null,
    result: 'lost',
    our_rank: 3,
    valid_count: 5,
    participant_count: 6,
    our_bid_amount: 85_000_000,
    our_bid_rate: 89.9,
    our_total_score: null,
    remark: '정상',
    winner_bizno: THEM,
    winner_name: '가온데이터(주)',
    award_amount: 80_000_000,
    fetched: true,
    bid_id: null,
    ...over,
  }
}

const LIST = {
  items: [
    bid('R26BK00000001', { result: 'won', our_rank: 1, winner_bizno: US, winner_name: '(주)예시컴퍼니' }),
    bid('R26BK00000002'),
    bid('R26BK00000003', { result: 'disqualified', our_rank: null, valid_count: 4, remark: '낙찰하한선 미달' }),
  ],
  next_cursor: null,
  counts: { all: 3, won: 1, lost: 2 },
  scan: { since: '2026-11-17T03:00:00Z', fetched_notices: 240, award_notices: 181_496 },
}

describe("우리 수주 현황 '투찰 결과' 탭", () => {
  it('낙찰·탈락·부적격을 순위나 사유와 함께 보여 주고, 탈락만 걸러 볼 수 있다', async () => {
    const api = mockApi({
      'GET /api/v1/awards/summary': json(SUMMARY),
      'GET /api/v1/my-bids': (_init, url) =>
        json(url.includes('result=lost') ? { ...LIST, items: LIST.items.slice(1) } : LIST),
    })
    m = await mountAt('/my-awards?tab=bids')
    await settle()
    const t = text(m.wrapper)
    for (const s of [
      copy.myBids.filterAll(3),
      copy.myBids.filterWon(1),
      copy.myBids.filterLost(2),
      copy.myBids.scan('2026-11-17', 240, 181_496),
    ])
      expect(t).toContain(s)
    const rows = m.wrapper.findAll('[data-my-bids] tbody tr')
    expect(rows.map((r) => r.get('[data-rank]').text())).toEqual([
      copy.myBids.rank(1, 5),
      copy.myBids.rank(3, 5),
      `${copy.myBids.noRank} · 낙찰하한선 미달`,
    ])
    expect(rows[2]!.text()).toContain(copy.myBids.disqualified)
    // 낙찰 업체는 비교 화면으로, 사업명은 상세로
    expect(rows[1]!.find(`a[href="/competitors/${THEM}"]`).exists()).toBe(true)
    expect(rows[1]!.find('a[href="/my-awards/bids/R26BK00000002/000/0/000"]').exists()).toBe(true)

    const lost = m.wrapper.findAll('label').find((l) => l.text() === copy.myBids.filterLost(2))!
    await lost.get('input').setValue(true)
    await settle()
    expect(m.router.currentRoute.value.query.result).toBe('lost')
    expect(api.calls.some((c) => c.url.includes('/my-bids?result=lost'))).toBe(true)
    expect(m.wrapper.findAll('[data-my-bids] tbody tr')).toHaveLength(2)
  })

  it('공동수급 구성원 낙찰은 낙찰로 보이고 역할·지분·대표사를 함께 보인다', async () => {
    mockApi({
      'GET /api/v1/awards/summary': json(SUMMARY),
      'GET /api/v1/my-bids': json({
        ...LIST,
        items: [
          bid('R26BK00000009', {
            result: 'won',
            our_rank: null,
            fetched: false,
            our_role: 'member',
            our_share: 18.9,
            winner_name: '(주)라임솔루션',
          }),
        ],
        counts: { all: 1, won: 1, lost: 0 },
      }),
    })
    m = await mountAt('/my-awards?tab=bids')
    await settle()
    const row = m.wrapper.get('[data-my-bids] tbody tr')
    expect(row.text()).toContain(copy.myBids.won)
    expect(row.text()).toContain(copy.awards.roleMember(formatPct(18.9)))
    expect(row.text()).toContain(copy.awards.leadBy('(주)라임솔루션'))
    expect(row.findAll('td')[4]!.text()).not.toBe(copy.myBids.us)
    expect(row.text()).not.toContain('89.9%') // 우리 투찰률도 없다
    // 직접 투찰하지 않았으므로 투찰금액 대신 우리 지분 금액(8,000만 × 18.9%)
    expect(row.get('[data-our-share-amount]').text()).toContain(formatMoney(Math.round(80_000_000 * 0.189)))
  })

  it('엑셀 다운로드는 화면 조건 그대로 요청하고 한국 날짜 파일 이름으로 저장한다', async () => {
    const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    const api = mockApi({
      'GET /api/v1/awards/summary': json(SUMMARY),
      'GET /api/v1/my-bids': json(LIST),
      'GET /api/v1/my-bids/export': () => new Response('x', { status: 200, headers: { 'content-type': XLSX } }),
    })
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} }))
    const names: string[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      names.push(this.download)
    })
    m = await mountAt('/my-awards?tab=bids&result=lost')
    await settle()
    const btn = m.wrapper.get('[data-my-bids-export]')
    expect(btn.text()).toContain(copy.myBids.exportButton)
    await btn.trigger('click')
    await settle()
    const call = api.calls.find((c) => c.url.startsWith('/api/v1/my-bids/export'))!
    expect(call.url).toBe('/api/v1/my-bids/export?result=lost')
    expect(names).toEqual([myBidsExportFilename(new Date())])
    vi.restoreAllMocks()
  })

  it('목록이 비면 엑셀 다운로드를 누를 수 없다', async () => {
    mockApi({
      'GET /api/v1/awards/summary': json(SUMMARY),
      'GET /api/v1/my-bids': json({ ...LIST, items: [], counts: { all: 0, won: 0, lost: 0 } }),
    })
    m = await mountAt('/my-awards?tab=bids')
    await settle()
    expect(m.wrapper.get('[data-my-bids-export]').attributes('disabled')).toBeDefined()
  })

  it('엑셀 파일 이름은 한국 날짜 기준', () => {
    expect(myBidsExportFilename(new Date('2026-11-24T16:00:00Z'))).toBe('2026-11-25_투찰 결과.xlsx')
  })

  it('낙찰 현황 탭이 기본이고 투찰 결과는 탭을 열 때만 부른다', async () => {
    const api = mockApi({
      'GET /api/v1/awards/summary': json(SUMMARY),
      'GET /api/v1/awards': json({ period: PERIOD, total: 0, next_cursor: null, items: [] }),
    })
    m = await mountAt('/my-awards')
    await settle()
    expect(api.calls.some((c) => c.url.includes('/my-bids'))).toBe(false)
    expect(m.wrapper.findAll('[role="tab"]').map((x) => x.text())).toEqual([copy.myBids.tabAwards, copy.myBids.tabBids])
  })
})

describe('투찰 결과 상세', () => {
  const DETAIL = {
    item: bid('R26BK00000003', { result: 'disqualified', our_rank: null, valid_count: 1, remark: '낙찰하한선 미달' }),
    estimated_price: 100_000_000,
    award_ratio: 0.8,
    g2b_award_rate: 88.1,
    is_joint: false,
    participants: [
      {
        rank: 1,
        bizno: THEM,
        name: '가온데이터(주)',
        bid_amount: 80_000_000,
        bid_rate: 88.1,
        tech_score: null,
        price_score: null,
        total_score: null,
        remark: '정상',
        is_winner: true,
        is_us: false,
        award_count: 12,
      },
      {
        rank: null,
        bizno: US,
        name: '(주)예시컴퍼니',
        bid_amount: 70_000_000,
        bid_rate: 80,
        tech_score: null,
        price_score: null,
        total_score: null,
        remark: '낙찰하한선 미달',
        is_winner: false,
        is_us: true,
        award_count: 3,
      },
    ],
    budget_exhausted: false,
    failed: false,
  }

  it('우리 결과·낙찰 업체·참가 업체 전체(비고·낙찰 수·비교 링크)를 보여 준다', async () => {
    mockApi({ 'GET /api/v1/my-bids/R26BK00000003/000/0/000': json(DETAIL) })
    m = await mountAt('/my-awards/bids/R26BK00000003/000/0/000')
    await settle()
    expect(m.wrapper.get('[data-our-result]').text()).toContain(`${copy.myBids.noRank} · 낙찰하한선 미달`)
    expect(m.wrapper.get('[data-winner]').find(`a[href="/competitors/${THEM}"]`).exists()).toBe(true)
    const rows = m.wrapper.findAll('[data-participants] tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.text()).toContain(copy.myBids.awardsCount(12))
    expect(rows[0]!.find(`a[href="/competitors/${THEM}"]`).text()).toBe(copy.myBids.compare)
    expect(rows[1]!.attributes('data-us')).toBe('true')
    expect(rows[1]!.text()).toContain('낙찰하한선 미달')
    expect(rows[1]!.find('a').exists()).toBe(false) // 우리 행에는 비교 링크 없음
    expect(text(m.wrapper)).toContain(copy.myBids.rankHelp)
  })

  it('개찰 결과를 못 불러왔으면 이유를 알린다', async () => {
    mockApi({
      'GET /api/v1/my-bids/R26BK00000003/000/0/000': json({ ...DETAIL, participants: null, budget_exhausted: true }),
    })
    m = await mountAt('/my-awards/bids/R26BK00000003/000/0/000')
    await settle()
    expect(text(m.wrapper)).toContain(copy.myBids.budget)
  })
})

describe('rankText', () => {
  it('순위가 있으면 유효 업체 수와, 없으면 사유와, 개찰 결과 전이면 상세 안내', () => {
    expect(rankText(bid('A'))).toBe(copy.myBids.rank(3, 5))
    expect(rankText(bid('A', { our_rank: null, remark: '협상평가부적격자', result: 'disqualified' }))).toBe(
      `${copy.myBids.noRank} · 협상평가부적격자`,
    )
    expect(rankText(bid('A', { our_rank: null, fetched: false, result: 'won' }))).toBe(copy.myBids.rankLater)
  })
})

// 우리 수주 현황 필터(2026-11-24): 낙찰 목록·투찰 결과를 연도·기간·사업명으로 좁힌다.
// 연도를 고르면 그해 1/1~12/31, 날짜를 직접 고칠 수도 있고, 사업명은 Enter(검색)로 적용한다.
import type { DOMWrapper } from '@vue/test-utils'
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
const SUMMARY = {
  bizno: '1234567890',
  name: '(주)예시컴퍼니',
  is_us: true,
  period: PERIOD,
  count: 2,
  amount_sum: 0,
  amount_avg: 0,
  org_count: 0,
  g2b_rate_median: null,
  ratio_median: null,
  ratio_known: 0,
  joint_count: 0,
  first_at: null,
  last_at: null,
  by_year: [
    { year: 2025, count: 1, amount_sum: 0, collecting: false },
    { year: 2026, count: 1, amount_sum: 0, collecting: false },
  ],
  by_org: [],
  by_field: [],
  fields: [],
}
const EMPTY_AWARDS = { period: PERIOD, total: 0, next_cursor: null, items: [] }
const EMPTY_BIDS = { items: [], next_cursor: null, counts: { all: 0, won: 0, lost: 0 }, scan: { since: null, fetched_notices: 0, award_notices: 0 } }

type Scope = Pick<DOMWrapper<Element>, 'get' | 'find'>
const params = (url: string) => new URL(url, 'http://x').searchParams
const lastOf = <T>(xs: T[]): T => xs[xs.length - 1]!
const field = (scope: Scope, name: string) => scope.get(`[data-filter-${name}]`)

async function setDate(scope: Scope, name: 'from' | 'to', v: string) {
  await field(scope, name).get('input').setValue(v)
  await settle()
}

async function search(scope: Scope, q: string) {
  await field(scope, 'search').get('input').setValue(q)
  await field(scope, 'search').trigger('submit')
  await settle()
}

describe('낙찰 목록 필터', () => {
  it('연도·기간·사업명이 요청에 실리고, 초기화하면 모두 빠진다', async () => {
    const api = mockApi({ 'GET /api/v1/awards/summary': json(SUMMARY), 'GET /api/v1/awards': json(EMPTY_AWARDS) })
    m = await mountAt('/my-awards')
    await settle()
    const box = m.wrapper.get('[data-awards-filter]')
    const last = () => params(lastOf(api.calls.filter((c) => c.url.startsWith('/api/v1/awards?') || c.url === '/api/v1/awards')).url)

    // 연도 보기는 최근 해부터, 고르면 그해 전체
    const year = field(box, 'year').get('select')
    expect(year.findAll('option').map((o) => o.text())).toEqual([copy.awardFilter.allYears, copy.awardFilter.year(2026), copy.awardFilter.year(2025)])
    await year.setValue('2025')
    await settle()
    expect([last().get('from'), last().get('to')]).toEqual(['2025-01-01', '2025-12-31'])
    expect((field(box, 'from').get('input').element as HTMLInputElement).value).toBe('2025-01-01')

    // 날짜를 직접 고치면 연도는 '직접 지정'
    await setDate(box, 'from', '2025-03-01')
    expect([last().get('from'), last().get('to')]).toEqual(['2025-03-01', '2025-12-31'])
    expect((year.element as HTMLSelectElement).value).toBe('custom')

    // 사업명은 Enter로 적용
    await search(box, '데이터 정비')
    expect(last().get('q')).toBe('데이터 정비')
    expect(text(m.wrapper)).toContain(copy.awards.emptyFiltered)

    await box.get('[data-filter-reset]').trigger('click')
    await settle()
    expect([last().get('from'), last().get('to'), last().get('q')]).toEqual([null, null, null])
    expect(box.find('[data-filter-reset]').exists()).toBe(false)
  })

  it('다른 화면(업체 검색)의 낙찰 목록에는 필터가 없다', async () => {
    mockApi({
      'GET /api/v1/companies/2345678901': json({ ...SUMMARY, bizno: '2345678901', is_us: false }),
      'GET /api/v1/awards': json(EMPTY_AWARDS),
      'GET /api/v1/competitors/watch': json({ items: [], team: [] }),
    })
    m = await mountAt('/companies?bizno=2345678901')
    await settle()
    expect(m.wrapper.find('[data-awards-filter]').exists()).toBe(false)
  })
})

describe('투찰 결과 필터', () => {
  it('기간·사업명이 요청에 실리고, 시작일이 종료일보다 늦으면 안내만 하고 부르지 않는다', async () => {
    const api = mockApi({ 'GET /api/v1/awards/summary': json(SUMMARY), 'GET /api/v1/my-bids': json(EMPTY_BIDS) })
    m = await mountAt('/my-awards?tab=bids')
    await settle()
    const box = m.wrapper.get('[data-awards-filter]')
    const bidCalls = () => api.calls.filter((c) => c.url.startsWith('/api/v1/my-bids'))
    const last = () => params(lastOf(bidCalls()).url)

    await field(box, 'year').get('select').setValue('2026')
    await settle()
    await search(box, '청사 청소')
    expect([last().get('from'), last().get('to'), last().get('q'), last().get('result')]).toEqual([
      '2026-01-01',
      '2026-12-31',
      '청사 청소',
      'all',
    ])
    expect(text(m.wrapper)).toContain(copy.myBids.emptyFiltered)

    const before = bidCalls().length
    await setDate(box, 'to', '2025-12-31') // 시작일(2026-01-01)보다 이르다
    expect(box.get('[role="alert"]').text()).toBe(copy.awardFilter.badRange)
    expect(bidCalls()).toHaveLength(before)
  })
})

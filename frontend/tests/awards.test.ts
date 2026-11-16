// P9 화면 (SPEC §15.7): 우리 수주 현황, 업체 검색, 회사 설정.
import type { VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { keywordsToText, parseKeywords } from '@/api/awards'
import { copy } from '@/copy'
import { ADMIN, json, mockApi, mountAt, settle, text, type Mounted } from './helpers'

function byLabel(w: VueWrapper, label: string) {
  const l = w.findAll('label').find((x) => x.text() === label)
  if (!l) throw new Error(`label not found: ${label}`)
  return w.get(`[id="${l.attributes('for')}"]`)
}

let m: Mounted | null = null
beforeEach(() => {
  document.body.innerHTML = ''
})
afterEach(() => {
  m?.wrapper.unmount()
  m = null
  vi.unstubAllGlobals()
})

const PERIOD = { from: '2021-11-11', to: '2026-11-10', counted_from: '2024-04-01', counted_to: '2026-11-10', collecting: true }

function summary(over: Record<string, unknown> = {}) {
  return {
    bizno: '1234567890',
    name: '(주)예시컴퍼니',
    is_us: true,
    period: PERIOD,
    count: 3,
    amount_sum: 160_000_000,
    amount_avg: 53_333_333,
    org_count: 2,
    g2b_rate_median: 87.5,
    ratio_median: 0.8,
    ratio_known: 1,
    joint_count: 0,
    first_at: '2025-01-01T00:00:00Z',
    last_at: '2026-11-01T00:00:00Z',
    by_year: [
      { year: 2022, count: null, amount_sum: null, collecting: true },
      { year: 2025, count: 1, amount_sum: 50_000_000, collecting: false },
      { year: 2026, count: 2, amount_sum: 110_000_000, collecting: false },
    ],
    by_org: [{ dminstt_cd: '1111111', dminstt_name: '행정안전부', count: 2, amount_sum: 130_000_000 }],
    by_field: [{ field: '데이터 정비', count: 1 }],
    fields: ['데이터 정비'],
    ...over,
  }
}

function award(no: string, over: Record<string, unknown> = {}) {
  return {
    bid_ntce_no: no,
    bid_ntce_ord: '000',
    title: `사업 ${no}`,
    bizno: '1234567890',
    winner_name: '(주)예시컴퍼니',
    award_amount: 80_000_000,
    g2b_award_rate: null,
    estimated_price: null,
    award_ratio: null,
    participant_count: 3,
    dminstt_cd: '1111111',
    dminstt_name: '행정안전부',
    opened_at: null,
    awarded_on: '2026-11-01',
    registered_at: '2026-11-01T01:00:00Z',
    fields: [],
    is_joint: false,
    bid_id: null,
    ...over,
  }
}

describe('우리 수주 현황 (/my-awards)', () => {
  it('회사가 없으면 빈 상태, 관리자에게는 회사 설정 링크', async () => {
    mockApi(
      {
        'GET /api/v1/awards/summary': json(
          { error: { code: 'not_configured', message: '', details: [] } },
          404,
        ),
      },
      ADMIN,
    )
    m = await mountAt('/my-awards')
    expect(text(m.wrapper)).toContain(copy.awards.notConfiguredTitle)
    expect(m.wrapper.get('a[href="/admin/company"]').text()).toBe(copy.awards.goCompanySettings)
  })

  it('요약·연도별(수집 중은 0이 아님)·비율 표시 규칙·더 보기', async () => {
    const api = mockApi({
      'GET /api/v1/awards/summary': json(summary()),
      'GET /api/v1/awards': (_i, url) =>
        url.includes('cursor=c2')
          ? json({ period: PERIOD, total: 3, next_cursor: null, items: [award('R3')] })
          : json({
              period: PERIOD,
              total: 3,
              next_cursor: 'c2',
              items: [
                award('R1', { award_ratio: 0.8, estimated_price: 100_000_000, g2b_award_rate: 87.5, bid_id: 'b7' }),
                award('R2', { g2b_award_rate: 87.5 }),
              ],
            }),
    })
    m = await mountAt('/my-awards')
    const t = text(m.wrapper)
    for (const s of [
      '(주)예시컴퍼니',
      copy.awards.basis,
      copy.awards.collectingFrom('2024-04-01'),
      copy.awards.countUnit(3),
      '1.6억',
      copy.awards.orgUnit(2),
      '행정안전부',
      copy.awards.internalOnly,
    ])
      expect(t).toContain(s)
    const y2022 = m.wrapper.get('[data-year="2022"]').text()
    expect(y2022).toContain(copy.awards.collecting)
    expect(y2022).not.toContain(copy.awards.countUnit(0))
    const rates = m.wrapper.findAll('[data-rate]').map((r) => r.text())
    expect(rates).toEqual([copy.awards.ratio('80'), copy.awards.g2bRate('87.5')])
    expect(m.wrapper.get('a[href="/bids/b7"]').text()).toBe('사업 R1')

    await m.wrapper.findAll('button').find((b) => b.text() === copy.awards.loadMore)!.trigger('click')
    await settle()
    expect(m.wrapper.findAll('[data-rate]').map((r) => r.text())).toContain(copy.awards.noRate)
    expect(api.calls.filter((c) => c.url.startsWith('/api/v1/awards?')).slice(-1)[0]!.url).toContain('cursor=c2')
  })

  it('분야 태그를 누르면 그 분야로 목록을 다시 불러온다', async () => {
    const api = mockApi({
      'GET /api/v1/awards/summary': json(summary()),
      'GET /api/v1/awards': json({ period: PERIOD, total: 0, next_cursor: null, items: [] }),
    })
    m = await mountAt('/my-awards')
    expect(text(m.wrapper)).toContain(copy.awards.emptyList)
    await m.wrapper.get('[data-field-chip]').trigger('click')
    await settle()
    const last = api.calls.filter((c) => c.url.startsWith('/api/v1/awards?')).slice(-1)[0]!
    expect(new URL(last.url, 'http://x').searchParams.get('field')).toBe('데이터 정비')
  })
})

describe('업체 검색 (/companies)', () => {
  it('찾고 고르면 URL에 남고 요약·목록이 나온다', async () => {
    const api = mockApi({
      'GET /api/v1/companies/search': json({
        items: [
          { bizno: '2345678901', name: '가온데이터시스템(주)', award_count: 12, last_award_at: '2026-10-01T00:00:00Z', is_us: false },
        ],
      }),
      'GET /api/v1/companies/2345678901': json(summary({ bizno: '2345678901', name: '가온데이터시스템(주)', is_us: false })),
      'GET /api/v1/awards': json({ period: PERIOD, total: 1, next_cursor: null, items: [award('R9')] }),
    })
    m = await mountAt('/companies')
    expect(text(m.wrapper)).toContain(copy.companies.pick)
    await byLabel(m.wrapper, copy.companies.searchLabel).setValue('가')
    await m.wrapper.get('form[role="search"]').trigger('submit')
    await settle()
    expect(text(m.wrapper)).toContain(copy.companies.tooShort)
    expect(api.calls.some((c) => c.url.startsWith('/api/v1/companies/search'))).toBe(false)

    await byLabel(m.wrapper, copy.companies.searchLabel).setValue('가온')
    await m.wrapper.get('form[role="search"]').trigger('submit')
    await settle()
    expect(m.router.currentRoute.value.query.q).toBe('가온')
    expect(text(m.wrapper)).toContain(copy.companies.awardCount(12))
    await m.wrapper.get('[data-company-hit]').trigger('click')
    await settle()
    expect(m.router.currentRoute.value.query.bizno).toBe('2345678901')
    expect(text(m.wrapper)).toContain(copy.companies.biznoLabel('234-56-78901'))
    expect(text(m.wrapper)).toContain('사업 R9')
    expect(api.calls.find((c) => c.url.startsWith('/api/v1/awards?'))!.url).toContain('bizno=2345678901')
  })
})

describe('회사 설정 (/admin/company)', () => {
  const STATUS = {
    configured: false,
    our_bizno: null,
    our_name: null,
    field_keywords: {},
    backfill_years: 5,
    updated_at: null,
    coverage: { covered_from: '2024-03-31T15:00:00Z', covered_to: '2026-11-10T00:00:00Z', target_from: '2021-11-11T00:00:00Z', collecting: true },
    years: [
      { year: 2023, ratio: 0 },
      { year: 2024, ratio: 0.75 },
      { year: 2025, ratio: 1 },
    ],
    calls_today: 12,
    calls_budget: 300,
    unidentified_count: 2,
    reclassify_started: false,
  }

  it('회원에게는 403 화면, /company는 /admin/company로', async () => {
    mockApi({ 'GET /api/v1/company': json(STATUS) })
    m = await mountAt('/company')
    expect(m.router.currentRoute.value.path).toBe('/admin/company')
    expect(text(m.wrapper)).toContain(copy.page.forbiddenTitle)
  })

  it('사업자번호로 이름을 채우고, 분야 키워드·기간을 저장한다', async () => {
    const api = mockApi(
      {
        'GET /api/v1/company': json(STATUS),
        'POST /api/v1/admin/company/lookup': json({ found: true, bizno: '1234567890', name: '(주)예시컴퍼니', award_count: 7 }),
        'PUT /api/v1/admin/company': (init) => json({ ...STATUS, ...JSON.parse(init.body as string), configured: true, reclassify_started: true }),
      },
      ADMIN,
    )
    m = await mountAt('/admin/company')
    const t = text(m.wrapper)
    for (const s of ['2024-04-01', copy.company.calls(12, 300), copy.awards.unidentified(2), copy.company.done, '75%'])
      expect(t).toContain(s)

    await byLabel(m.wrapper, copy.company.bizno).setValue('123-45-67890')
    await m.wrapper.findAll('button').find((b) => b.text() === copy.company.lookup)!.trigger('click')
    await settle()
    expect((byLabel(m.wrapper, copy.company.name).element as HTMLInputElement).value).toBe('(주)예시컴퍼니')
    expect(m.wrapper.get('[data-lookup]').text()).toBe(copy.company.found('(주)예시컴퍼니', 7))

    await byLabel(m.wrapper, copy.company.fields).setValue('잘못된 줄')
    await m.wrapper.get(`form[aria-label="${copy.company.title}"]`).trigger('submit')
    await settle()
    expect(text(m.wrapper)).toContain(copy.company.fieldsInvalid(1))
    expect(api.calls.some((c) => c.method === 'PUT')).toBe(false)

    await byLabel(m.wrapper, copy.company.fields).setValue('데이터 정비: 데이터 정비, DB 구축\n\nAI 분석: AI')
    await byLabel(m.wrapper, copy.company.years).setValue(7)
    await m.wrapper.get(`form[aria-label="${copy.company.title}"]`).trigger('submit')
    await settle()
    const put = api.calls.find((c) => c.method === 'PUT')!
    expect(put.body).toEqual({
      our_bizno: '1234567890',
      our_name: '(주)예시컴퍼니',
      field_keywords: { '데이터 정비': ['데이터 정비', 'DB 구축'], 'AI 분석': ['AI'] },
      backfill_years: 7,
    })
    expect(text(m.wrapper)).toContain(copy.company.reclassifying)
  })
})

describe('분야 키워드 글 ↔ 사전', () => {
  it('왕복하고 잘못된 줄 번호를 알려 준다', () => {
    const k = { A: ['a', 'b'], B: ['c'] }
    expect(parseKeywords(keywordsToText(k))).toEqual({ value: k })
    expect(parseKeywords('A: a\nB')).toEqual({ errorLine: 2 })
    expect(parseKeywords('A: ,')).toEqual({ errorLine: 1 })
    expect(parseKeywords('A: a\nA: b, a')).toEqual({ value: { A: ['a', 'b'] } })
  })
})

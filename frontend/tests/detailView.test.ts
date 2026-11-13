// §7.5 공고 상세·분석: 헤더·첨부·요약, SSE 분석 단계와 결과 순서, 경고 배너, 공고번호로 열기, 기록 열기.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { copy } from '@/copy'
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

const DETAIL = {
  ...card({ revision: 2 }),
  prespec_reg_no: 'R26BD00000077',
  related_bid_id: 'b300',
  files: [
    { file_id: 11, name: '제안요청서.hwp', kind: 'rfp', status: 'ok' },
    { file_id: 12, name: '과업지시서.pdf', kind: 'spec', status: 'failed' },
  ],
  summary: null,
  my_analysis_id: null,
}

const ANALYSIS = {
  overview: '민원 데이터를 분석하는 시스템을 구축한다.',
  requirements: [{ text: '형태소 분석', kind: 'technical', evidence: null, source: '제안요청서.hwp' }],
  evaluation: { method: '협상에 의한 계약', items: [{ name: '기술', points: 90, note: null }] },
  schedule: [{ label: '제안서 제출', date: '2026-11-20', raw: null }],
  budget_contract: { budget_text: '1.2억원', contract_method: null, payment_terms: null, period: '6개월' },
  risks: [{ text: '일정이 촉박', severity: 'high', source: null }],
  fit: { score: 82, verdict: 'strong', strengths: ['검색 경험'], gaps: ['공공 실적'], reasoning: '주력 일치' },
  next_actions: ['참가자격 확인'],
  warnings: ['첨부 문서를 읽지 못함'],
}

function base(extra: Record<string, unknown> = {}) {
  return {
    'GET /api/v1/bids/b101': json(DETAIL),
    'GET /api/v1/profiles': json({ items: [profile()] }),
    ...extra,
  }
}

describe('BidDetailView', () => {
  it('G2B 공고 정보는 요약과 따로, 원 단위 그대로 (decisions/2026-11-13-official-facts)', async () => {
    mockApi(
      base({
        'GET /api/v1/bids/b101': json({
          ...DETAIL,
          summary: {
            headline: '연계 개선',
            overview: '시스템을 개선한다.',
            key_requirements: [],
            evaluation: { method: null, items: [] },
            schedule: [],
            budget_contract: { budget_text: null, contract_method: null, payment_terms: null, period: null },
            eligibility: [],
            risks: [],
            keywords: [],
            coverage: { files_read: 1, files_total: 1, truncated: false, warnings: [] },
          },
          official: {
            deadline_label: '입찰 마감',
            deadline_at: '2026-11-24T01:00:00Z',
            opening_at: '2026-11-24T02:00:00Z',
            assigned_budget: 99000000,
            estimated_price: 90000000,
            contract_method: '제한경쟁',
            award_method: '협상에 의한 낙찰자 결정',
          },
        }),
      }),
    )
    m = await mountAt('/bids/b101')
    const box = m.wrapper.get('[data-official]')
    const t = box.text()
    for (const s of [
      copy.official.title,
      '입찰 마감',
      '2026-11-24 10:00',
      copy.official.opening,
      '99,000,000원',
      copy.official.assignedBudget,
      '90,000,000원',
      '제한경쟁',
      '협상에 의한 낙찰자 결정',
    ])
      expect(t).toContain(s)
    expect(text(m.wrapper)).toContain(copy.official.aiNote) // 요약은 AI가 정리했다는 안내
    expect(t).not.toContain(copy.official.docBudgetTitle) // 원문 금액이 G2B와 같으면 따로 안 보인다
  })

  it('첨부 문서의 사업금액이 G2B 배정예산과 다르면 둘 다 보인다', async () => {
    const official = {
      deadline_label: '의견 등록 마감',
      deadline_at: '2026-11-15T14:59:00Z',
      opening_at: null,
      assigned_budget: 670900400,
      estimated_price: null,
      contract_method: null,
      award_method: null,
    }
    const doc_budgets = [{ file: '제안요청서.hwp', label: '사업금액', amount: 665000000 }]
    mockApi(base({ 'GET /api/v1/bids/b101': json({ ...DETAIL, official, doc_budgets }) }))
    m = await mountAt('/bids/b101')
    const t = m.wrapper.get('[data-official]').text()
    for (const s of ['670,900,400원', copy.official.docBudgetTitle, '665,000,000원', '제안요청서.hwp', '사업금액'])
      expect(t).toContain(s)
  })

  it('헤더·배지·관련 사전규격·첨부 상태·요약 안내', async () => {
    mockApi(base())
    m = await mountAt('/bids/b101')
    const t = text(m.wrapper)
    expect(t).toContain(DETAIL.title)
    expect(t).toContain(copy.bid.revised)
    expect(t).toContain(copy.detail.fileStatus.ok)
    expect(t).toContain(copy.detail.fileStatus.failed)
    expect(t).toContain(copy.detail.summaryHint)
    expect(m.wrapper.get('a[href="/bids/b300"]').text()).toContain(copy.bid.relatedPrespec)
  })

  it('요약 카드에 제목줄·개요와 일정·예산 같은 구조화 정보를 보여 준다', async () => {
    const summary = {
      headline: '민원 분석 시스템 구축',
      overview: '민원 데이터를 분석한다.',
      key_requirements: [],
      evaluation: { method: null, items: [] },
      schedule: [{ label: '제안서 제출 마감', date: '2026-11-30', raw: null }],
      budget_contract: { budget_text: '금 99,000,000원', contract_method: null, payment_terms: null, period: null },
      eligibility: [],
      risks: [],
      keywords: [],
      coverage: { files_read: 1, files_total: 2, truncated: false, warnings: [] },
    }
    mockApi(base({ 'GET /api/v1/bids/b101': json({ ...DETAIL, summary }) }))
    m = await mountAt('/bids/b101')
    const t = text(m.wrapper)
    for (const s of [summary.headline, summary.overview, '제안서 제출 마감', '2026-11-30', '금 99,000,000원']) {
      expect(t).toContain(s)
    }
    expect(t).not.toContain(copy.detail.summaryHint)
  })

  it('첨부를 누르면 본문 일부를 드로어로 보여 준다', async () => {
    mockApi(
      base({
        'GET /api/v1/bids/b101/files/11/text': json({
          file_id: 11,
          name: '제안요청서.hwp',
          text: '제1조 목적',
          char_count: 50000,
          truncated: true,
        }),
      }),
    )
    m = await mountAt('/bids/b101')
    await m.wrapper.get(`button[aria-label="${copy.detail.previewOpen('제안요청서.hwp')}"]`).trigger('click')
    await settle()
    expect(document.body.textContent).toContain('제1조 목적')
    expect(document.body.textContent).toContain(copy.detail.previewTruncated)
  })

  it('첨부 이름을 누르면 원본을 내려받고, 본문 보기는 읽은 파일에만 아이콘으로 있다', async () => {
    const api = mockApi(
      base({
        'GET /api/v1/bids/b101/files/12/download': new Response('%PDF', {
          status: 200,
          headers: { 'content-type': 'application/octet-stream' },
        }),
      }),
    )
    const created = vi.fn(() => 'blob:fake')
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() }))
    const clicked: HTMLAnchorElement[] = []
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this)
    })
    m = await mountAt('/bids/b101')
    // 본문 보기: 읽은 파일(ok)만. 내려받기: 상태와 관계없이 모두
    expect(m.wrapper.findAll(`button[aria-label="${copy.detail.previewOpen('과업지시서.pdf')}"]`)).toHaveLength(0)
    expect(m.wrapper.find(`button[aria-label="${copy.detail.previewOpen('제안요청서.hwp')}"]`).exists()).toBe(true)
    await m.wrapper.get(`button[aria-label="${copy.detail.download('과업지시서.pdf')}"]`).trigger('click')
    await settle()
    expect(api.calls.some((c) => c.url.startsWith('/api/v1/bids/b101/files/12/download'))).toBe(true)
    expect(created).toHaveBeenCalledOnce()
    expect(clicked.map((a) => [a.href, a.download])).toEqual([['blob:fake', '과업지시서.pdf']])
    click.mockRestore()
  })

  it('첨부를 받지 못하면 안내 토스트', async () => {
    mockApi(
      base({
        'GET /api/v1/bids/b101/files/11/download': json(
          { error: { code: 'file_unavailable', message: 'x', details: [] } },
          502,
        ),
      }),
    )
    m = await mountAt('/bids/b101')
    await m.wrapper.get(`button[aria-label="${copy.detail.download('제안요청서.hwp')}"]`).trigger('click')
    await settle()
    expect(document.body.textContent).toContain(copy.common.fileUnavailable)
  })

  it('분석하기: 단계 표시 → 결과를 §7.5 순서로, 경고 배너, 피드백', async () => {
    const api = mockApi(
      base({
        'POST /api/v1/bids/b101/analyze': sse([
          { type: 'status', stage: 'files', message: '', cache: true },
          { type: 'status', stage: 'summarize', message: '', cache: false },
          { type: 'status', stage: 'analyze', message: '', cache: false },
          { type: 'result', analysis_id: 5, analysis: ANALYSIS, markdown: '## 사업 개요', from_cache: false },
          { type: 'done', usage: { llm_calls: 3, g2b_calls: 0, cache: {} } },
        ]),
      }),
    )
    m = await mountAt('/bids/b101')
    await m.wrapper.findAll('button').find((b) => b.text() === copy.detail.analyzeSubmit)!.trigger('click')
    await settle(10)
    expect(api.calls.find((c) => c.url.endsWith('/analyze'))?.body).toEqual({ profile_id: 7 })
    const headings = m.wrapper.findAll('h3').map((h) => h.text())
    const order: string[] = [
      copy.analysis.overview,
      copy.analysis.requirements,
      copy.analysis.evaluation,
      copy.analysis.schedule,
      copy.analysis.budget,
      copy.analysis.risks,
      copy.analysis.fit,
      copy.analysis.nextActions,
    ]
    expect(headings.filter((h) => order.includes(h))).toEqual(order)
    const t = text(m.wrapper)
    expect(t).toContain(copy.analyze.noText)
    expect(t).toContain(copy.analysis.source('제안요청서.hwp'))
    expect(t).toContain(copy.analysis.verdict.strong)
    expect(t).toContain(copy.feedback.label)
  })

  it('다른 요청이 처리 중이면 안내를 보여 준다', async () => {
    mockApi(
      base({
        'POST /api/v1/bids/b101/analyze': sse([
          { type: 'status', stage: 'summarize', message: '다른 요청이 처리 중입니다' },
          { type: 'error', code: 'in_progress', message: 'x' },
          { type: 'done', usage: { llm_calls: 0, g2b_calls: 0, cache: {} } },
        ]),
      }),
    )
    m = await mountAt('/bids/b101')
    await m.wrapper.findAll('button').find((b) => b.text() === copy.detail.analyzeSubmit)!.trigger('click')
    await settle(10)
    expect(text(m.wrapper)).toContain(copy.analyze.inProgress)
  })

  it('프로필이 없으면 만들기 안내', async () => {
    mockApi(base({ 'GET /api/v1/profiles': json({ items: [] }) }))
    m = await mountAt('/bids/b101')
    expect(text(m.wrapper)).toContain(copy.detail.profileRequired)
    expect(m.wrapper.find('a[href="/settings/profiles"]').exists()).toBe(true)
  })

  it('?analysis=로 내 분석 기록을 바로 연다', async () => {
    mockApi(
      base({
        'GET /api/v1/analyses/5': json({
          analysis_id: 5,
          bid_id: 'b101',
          profile_id: 7,
          analysis: { ...ANALYSIS, warnings: [] },
          markdown: '## 사업 개요',
          created_at: '2026-11-09T00:00:00Z',
        }),
      }),
    )
    m = await mountAt('/bids/b101?analysis=5')
    expect(text(m.wrapper)).toContain(ANALYSIS.overview)
  })

  it('공고번호로 열기: 찾으면 이동, 없으면 안내', async () => {
    mockApi(
      base({
        'GET /api/v1/bids/lookup': (_init: RequestInit, url: string) =>
          url.includes('R26BK00000202')
            ? json({ bid_id: 'b202' })
            : json({ error: { code: 'not_found', message: '' } }, 404),
        'GET /api/v1/bids/b202': json({ ...DETAIL, bid_id: 'b202', title: '두 번째 공고' }),
      }),
    )
    m = await mountAt('/bids/b101')
    const input = m.wrapper.get('input[name="bid_no"]')
    await input.setValue('R26BK00000999')
    const form = (input.element as HTMLInputElement).form!
    form.dispatchEvent(new Event('submit'))
    await settle()
    expect(text(m.wrapper)).toContain(copy.detail.lookupNotFound)
    await input.setValue('R26BK00000202')
    form.dispatchEvent(new Event('submit'))
    await settle()
    expect(m.router.currentRoute.value.path).toBe('/bids/b202')
  })

  it('공고번호가 아닌 글자는 키워드로 공고 검색에 넘긴다', async () => {
    const api = mockApi(base())
    m = await mountAt('/bids/b101')
    const input = m.wrapper.get('input[name="bid_no"]')
    await input.setValue('  AI 유지보수 ')
    ;(input.element as HTMLInputElement).form!.dispatchEvent(new Event('submit'))
    // /search는 지연 로딩이라 이동이 settle()보다 늦게 끝날 수 있다
    await vi.waitFor(() => expect(m!.router.currentRoute.value.path).toBe('/search'), { timeout: 5000 })
    expect(m.router.currentRoute.value.query.q).toBe('AI 유지보수')
    expect(api.calls.some((c) => c.url.includes('/bids/lookup'))).toBe(false)
  })

  it.each(['R26BK00000202', 'r26bd00273663', '20240512345-00', '20240512345'])(
    '공고번호 모양(%s)이면 번호로 찾는다',
    async (no) => {
      const api = mockApi(base({ 'GET /api/v1/bids/lookup': json({ bid_id: 'b202' }) }))
      m = await mountAt('/bids/b101')
      const input = m.wrapper.get('input[name="bid_no"]')
      await input.setValue(no)
      ;(input.element as HTMLInputElement).form!.dispatchEvent(new Event('submit'))
      await settle()
      expect(api.calls.some((c) => c.url.includes('/bids/lookup'))).toBe(true)
    },
  )

  it('공고번호로 열기: 나라장터 조회 실패는 번호 오류와 다르게 안내', async () => {
    mockApi(
      base({
        'GET /api/v1/bids/lookup': json({ error: { code: 'g2b_unavailable', message: '' } }, 503),
      }),
    )
    m = await mountAt('/bids/b101')
    const input = m.wrapper.get('input[name="bid_no"]')
    await input.setValue('R26BK00000999')
    ;(input.element as HTMLInputElement).form!.dispatchEvent(new Event('submit'))
    await settle()
    expect(text(m.wrapper)).toContain(copy.common.g2bUnavailable)
    expect(text(m.wrapper)).not.toContain(copy.detail.lookupNotFound)
  })

  it('없는 공고는 안내', async () => {
    mockApi({ 'GET /api/v1/profiles': json({ items: [] }) })
    m = await mountAt('/bids/b999')
    expect(text(m.wrapper)).toContain(copy.detail.notFound)
  })
})

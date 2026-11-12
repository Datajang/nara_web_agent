// §7.5-3 요약 카드의 구조화 정보: 일정·예산·계약·평가·자격·핵심 요구사항. 빈 항목은 숨긴다.
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { BidSummary } from '@/api/types'
import SummaryFacts from '@/components/bid/SummaryFacts.vue'
import { copy } from '@/copy'

function summary(extra: Partial<BidSummary> = {}): BidSummary {
  return {
    headline: '민원 분석 시스템 구축',
    overview: '민원 데이터를 분석한다.',
    key_requirements: [],
    evaluation: { method: null, items: [] },
    schedule: [],
    budget_contract: { budget_text: null, contract_method: null, payment_terms: null, period: null },
    eligibility: [],
    risks: [],
    keywords: [],
    coverage: { files_read: 1, files_total: 1, truncated: false, warnings: [] },
    ...extra,
  }
}

const req = (n: number) =>
  Array.from({ length: n }, (_, i) => ({ text: `요구사항 ${i + 1}`, kind: 'technical' as const, evidence: null, source: null }))

describe('SummaryFacts', () => {
  it('일정·예산·계약·평가·자격·요구사항을 보여 준다', () => {
    const w = mount(SummaryFacts, {
      props: {
        summary: summary({
          schedule: [
            { label: '제안서 제출 마감', date: '2026-11-30', raw: null },
            { label: '제안 발표', date: null, raw: '추후 통보' },
          ],
          budget_contract: { budget_text: '금 99,000,000원', contract_method: '협상에 의한 계약', payment_terms: null, period: '계약일로부터 3개월' },
          evaluation: { method: '기술 90 : 가격 10', items: [{ name: '기술능력평가', points: 90, note: null }] },
          eligibility: ['소프트웨어사업자 등록'],
          key_requirements: req(2),
        }),
      },
    })
    const t = w.text()
    for (const s of [
      copy.analysis.schedule, '제안서 제출 마감', '2026-11-30', '추후 통보',
      copy.analysis.budget, '금 99,000,000원', '협상에 의한 계약', '계약일로부터 3개월',
      copy.analysis.evaluation, '기술 90 : 가격 10', '기술능력평가', copy.analysis.points(90),
      copy.detail.eligibility, '소프트웨어사업자 등록',
      copy.analysis.requirements, '요구사항 1', '요구사항 2',
    ]) {
      expect(t).toContain(s)
    }
  })

  it('비어 있는 항목은 제목째 숨기고 "확인되지 않음"을 늘어놓지 않는다', () => {
    const w = mount(SummaryFacts, {
      props: { summary: summary({ schedule: [{ label: '입찰 마감', date: '2026-12-01', raw: null }] }) },
    })
    const t = w.text()
    expect(t).toContain(copy.analysis.schedule)
    for (const s of [copy.analysis.budget, copy.analysis.evaluation, copy.detail.eligibility, copy.analysis.requirements, copy.analysis.none]) {
      expect(t).not.toContain(s)
    }
  })

  it('모든 항목이 비면 아무것도 그리지 않는다', () => {
    const w = mount(SummaryFacts, { props: { summary: summary() } })
    expect(w.text()).toBe('')
  })

  it('핵심 요구사항은 5개까지 보이고 나머지는 접어 둔다', () => {
    const w = mount(SummaryFacts, { props: { summary: summary({ key_requirements: req(8) }) } })
    const details = w.get('details')
    expect(details.get('summary').text()).toBe(copy.detail.moreRequirements(3))
    expect(details.text()).toContain('요구사항 6')
    const shown = w.findAll('li').filter((li) => !details.element.contains(li.element))
    expect(shown.map((li) => li.text())).toEqual(['요구사항 1', '요구사항 2', '요구사항 3', '요구사항 4', '요구사항 5'])
  })

  it('문서에서 나온 글자는 HTML로 실행되지 않는다 (§7.11-5)', () => {
    const evil = '<img src=x onerror=alert(1)>마감'
    const w = mount(SummaryFacts, { props: { summary: summary({ schedule: [{ label: evil, date: null, raw: null }] }) } })
    expect(w.find('img').exists()).toBe(false)
    expect(w.text()).toContain(evil)
  })
})

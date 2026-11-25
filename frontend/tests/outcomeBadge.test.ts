// 마감 공고 사유 배지(2026-11-26): 종류별 문구·색. 진행 중(outcome null)이면 아무것도 그리지 않는다.
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import OutcomeBadge from '@/components/bid/OutcomeBadge.vue'
import type { BidOutcome } from '@/api/types'
import { copy } from '@/copy'
import { card, json, mockApi, mountAt, settle } from './helpers'

const o = (over: Partial<BidOutcome>): BidOutcome => ({
  kind: 'waiting',
  company: null,
  more: 0,
  reason: null,
  opening_at: null,
  ...over,
})
const render = (outcome: BidOutcome | null) => mount(OutcomeBadge, { props: { outcome } })

describe('OutcomeBadge', () => {
  it('종류마다 문구를 만든다', () => {
    const cases: [BidOutcome, string][] = [
      [o({ kind: 'awarded', company: '(주)가온데이터' }), copy.bid.outcome.awarded('(주)가온데이터', 0)],
      [o({ kind: 'awarded', company: '(주)가온', more: 2 }), '낙찰 · (주)가온 외 2'],
      [o({ kind: 'failed', reason: '무응찰' }), '유찰 · 무응찰'],
      [o({ kind: 'failed' }), '유찰'],
      [o({ kind: 'opened', company: '(주)다온' }), '개찰완료 · 1순위 (주)다온'],
      [o({ kind: 'rebid' }), '재입찰'],
      [o({ kind: 'before_opening', opening_at: '2026-11-28T01:00:00Z' }), '개찰 전 11.28 10:00'],
      [o({ kind: 'waiting' }), '결과 대기'],
      [o({ kind: 'prespec_closed' }), '의견 마감'],
    ]
    for (const [outcome, label] of cases) {
      const w = render(outcome)
      expect(w.text()).toBe(label)
      expect(w.get('[data-outcome]').attributes('title')).toBe(label)
    }
  })

  it('낙찰은 초록, 유찰은 빨강, 대기는 회색', () => {
    expect(render(o({ kind: 'awarded', company: 'x' })).html()).toContain('bg-success-bg')
    expect(render(o({ kind: 'failed' })).html()).toContain('bg-danger-bg')
    expect(render(o({ kind: 'rebid' })).html()).toContain('bg-warning-bg')
    expect(render(o({ kind: 'waiting' })).html()).toContain('bg-neutral-bg')
  })

  it('진행 중이면 그리지 않는다', () => {
    expect(render(null).find('[data-outcome]').exists()).toBe(false)
  })
})

describe('공고 카드의 마감 사유', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('보관함 북마크 목록에서 마감된 공고에 사유 배지가 보인다', async () => {
    const closed = card({ status: 'closed', bookmarked: true, outcome: o({ kind: 'failed', reason: '단독응찰' }) })
    const open = card({ bid_id: 'b102', title: '진행 중 공고', bookmarked: true, outcome: null })
    const row = (bid: ReturnType<typeof card>) => ({
      bid,
      note: '',
      analysis_id: null,
      created_at: '2026-11-09T00:00:00Z',
      notify_result: true,
    })
    mockApi({ 'GET /api/v1/bookmarks': json({ items: [row(closed), row(open)] }) })
    const m = await mountAt('/library?tab=bookmarks')
    await settle()
    const badges = m.wrapper.findAll('[data-outcome]')
    expect(badges.map((b) => b.text())).toEqual(['유찰 · 단독응찰'])
    m.wrapper.unmount()
  })
})

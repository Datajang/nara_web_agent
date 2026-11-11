// §10.4 도메인·UI 컴포넌트: 카드 XSS(§7.11-5), 마감·점수 배지 색 규칙(§10.1), 칩 입력, 단계 표시, 마크다운 정제.
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import BidCard from '@/components/bid/BidCard.vue'
import DeadlineBadge from '@/components/bid/DeadlineBadge.vue'
import ProgressSteps from '@/components/bid/ProgressSteps.vue'
import ScoreBadge from '@/components/bid/ScoreBadge.vue'
import ChipInput from '@/components/ui/ChipInput.vue'
import MarkdownView from '@/components/ui/MarkdownView.vue'
import { copy } from '@/copy'
import { card } from './helpers'

const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div/>' } }] })
const NOW = new Date('2026-11-10T06:00:00Z')

describe('BidCard', () => {
  it('제목의 HTML은 실행되지 않고 글자로 보인다 (§7.11-5)', () => {
    const evil = '<img src=x onerror=alert(1)>공고'
    const w = mount(BidCard, { props: { bid: card({ title: evil }) }, global: { plugins: [router] } })
    expect(w.find('img').exists()).toBe(false)
    expect(w.text()).toContain(evil)
  })

  it('구분·정정·취소·요약 배지와 원문 링크(새 탭, noopener)', () => {
    const w = mount(BidCard, {
      props: { bid: card({ source: 'prespec', revision: 2, cancelled: true, summary_ready: true }) },
      global: { plugins: [router] },
    })
    const t = w.text()
    for (const label of [copy.bid.prespec, copy.bid.revised, copy.bid.cancelled, copy.bid.summaryReady]) {
      expect(t).toContain(label)
    }
    const a = w.get('a[target="_blank"]')
    expect(a.attributes('rel')).toBe('noopener noreferrer')
    expect(w.get('a[href="/bids/b101"]').text()).toContain('AI 민원')
  })

  it('점수는 showScore일 때만, 근거와 함께', () => {
    const w = mount(BidCard, {
      props: { bid: card({ score: 85, reason: '주력 분야 일치' }), showScore: true },
      global: { plugins: [router] },
    })
    expect(w.text()).toContain('85')
    expect(w.text()).toContain('주력 분야 일치')
  })

  it('북마크 버튼은 라벨이 있고 toggle 이벤트를 낸다', async () => {
    const w = mount(BidCard, { props: { bid: card() }, global: { plugins: [router] } })
    const btn = w.get(`button[aria-label="${copy.bid.bookmarkAdd}"]`)
    await btn.trigger('click')
    expect(w.emitted('toggle-bookmark')).toHaveLength(1)
  })
})

describe('DeadlineBadge (§10.1 마감 색 규칙)', () => {
  const tone = (iso: string | null) =>
    mount(DeadlineBadge, { props: { deadlineAt: iso, now: NOW } }).get('span').attributes('data-tone')
  it.each([
    ['2026-11-25T00:00:00Z', 'neutral'], // 8일 이상
    ['2026-11-15T00:00:00Z', 'warning'], // 4~7일
    ['2026-11-12T00:00:00Z', 'danger'], // 3일 이내
    ['2026-11-09T00:00:00Z', 'neutral'], // 마감
    [null, 'neutral'], // 마감 미정
  ])('%s → %s', (iso, expected) => {
    expect(tone(iso)).toBe(expected)
  })
})

describe('ScoreBadge', () => {
  it.each([
    [85, copy.score.high, 'success'],
    [70, copy.score.mid, 'primary'],
    [30, copy.score.low, 'neutral'],
  ])('%i점 → %s', (score, label, tone) => {
    const w = mount(ScoreBadge, { props: { score } })
    expect(w.text()).toContain(label)
    expect(w.get('span').attributes('data-tone')).toBe(tone)
  })
})

describe('ChipInput', () => {
  it('Enter·쉼표로 추가, 공백·중복 제거, 최대 개수', async () => {
    const w = mount(ChipInput, { props: { label: '키워드', modelValue: [] as string[], max: 3 } })
    const input = w.get('input')
    const add = async (v: string, key = 'Enter') => {
      await input.setValue(v)
      await input.trigger('keydown', { key })
      const last = w.emitted('update:modelValue')?.slice(-1)[0]?.[0] as string[] | undefined
      if (last) await w.setProps({ modelValue: last })
    }
    await add(' AI ')
    await add('AI')
    await add('데이터', ',')
    await add('   ')
    await add('검색')
    await add('초과')
    expect(w.props('modelValue')).toEqual(['AI', '데이터', '검색'])
  })

  it('빈 입력에서 Backspace는 마지막 칩을 지운다', async () => {
    const w = mount(ChipInput, { props: { label: '키워드', modelValue: ['AI', '검색'] } })
    await w.get('input').trigger('keydown', { key: 'Backspace' })
    expect(w.emitted('update:modelValue')?.slice(-1)[0]?.[0]).toEqual(['AI'])
  })
})

describe('ProgressSteps', () => {
  it('단계를 한글로, 현재 단계 표시, 캐시 적중은 저장된 결과 사용', () => {
    const w = mount(ProgressSteps, {
      props: { stages: ['files', 'extract', 'summarize', 'analyze'], current: 'summarize', cached: ['files'] },
    })
    expect(w.text()).toContain(copy.stage.summarize)
    expect(w.get('[aria-current="step"]').text()).toContain(copy.stage.summarize)
    expect(w.text()).toContain(copy.stage.cached)
    expect(w.find('[aria-live="polite"]').exists()).toBe(true)
  })
})

describe('MarkdownView', () => {
  it('스크립트·이벤트 속성을 제거하고 링크는 새 탭', () => {
    const w = mount(MarkdownView, {
      props: { source: '## 제목\n\n<img src=x onerror=alert(1)><script>alert(1)</script>[링크](https://a.b)' },
    })
    const html = w.html()
    expect(html).not.toContain('onerror')
    expect(html).not.toContain('<script')
    expect(w.get('h2').text()).toBe('제목')
    expect(w.get('a').attributes('rel')).toBe('noopener noreferrer')
  })
})

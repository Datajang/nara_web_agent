// 분석 진행 로딩바 (§7.5-4): 조각 진행률·분석 예상 시간으로 %·남은 시간 계산.
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AnalyzeProgress from '@/components/bid/AnalyzeProgress.vue'
import { DEFAULT_ANALYZE_S, formatDuration, progressState, type Stamped } from '@/components/bid/progress'
import type { StreamEvent } from '@/api/types'
import { copy } from '@/copy'

const S = 1000

describe('progressState', () => {
  it('이벤트가 없으면 0%, 남은 시간 모름', () => {
    expect(progressState([], 0, 5 * S)).toEqual({ percent: 0, elapsedS: 5, remainingS: null })
  })

  it('요약 3/6: 10 + 60×½ = 40%, 남은 시간 = 조각 속도 × 남은 조각 + 합치기(첫 조각 × 1.5) + 분석 예상', () => {
    const st: Stamped[] = [
      { stage: 'files', at: 0 },
      { stage: 'summarize', progress: { done: 0, total: 6 }, at: 0 },
      { stage: 'summarize', progress: { done: 1, total: 6 }, at: 10 * S },
      { stage: 'summarize', progress: { done: 3, total: 6 }, at: 30 * S },
    ]
    expect(progressState(st, 0, 30 * S)).toEqual({ percent: 40, elapsedS: 30, remainingS: 135 })
  })

  it('조각을 다 읽은 뒤 합치는 동안에도 70→75%로 움직이고 남은 시간이 줄어든다 (실측 b565: 100초 멈춤)', () => {
    const st: Stamped[] = [
      { stage: 'summarize', progress: { done: 0, total: 2 }, at: 0 },
      { stage: 'summarize', progress: { done: 1, total: 2 }, at: 10 * S },
      { stage: 'summarize', progress: { done: 2, total: 2 }, at: 20 * S },
    ]
    // 합치기 예상 = 첫 조각 10초 × 1.5 = 15초. 6초 지남 → 남은 9초 + 분석 90초
    expect(progressState(st, 0, 26 * S)).toEqual({ percent: 72, elapsedS: 26, remainingS: 99 })
    expect(progressState(st, 0, 60 * S)).toMatchObject({ percent: 75, remainingS: 90 })
  })

  it('다른 요청의 요약을 기다리는 동안(진행률 없음)에도 10%에서 천천히 움직인다', () => {
    const st: Stamped[] = [{ stage: 'summarize', waiting: true, at: 0 }]
    expect(progressState(st, 0, 120 * S)).toMatchObject({ percent: 41, remainingS: null })
  })

  it('첫 조각을 읽는 동안에도 첫 칸(10→20%) 안에서 움직인다', () => {
    const st: Stamped[] = [{ stage: 'summarize', progress: { done: 0, total: 6 }, at: 0 }]
    expect(progressState(st, 0, 60 * S).percent).toBe(15)
    expect(progressState(st, 0, 600 * S).percent).toBeLessThan(20)
  })

  it('요약 중 남은 시간에는 서버가 준 분석 예상(expected_s)을 쓴다', () => {
    const st: Stamped[] = [
      { stage: 'summarize', progress: { done: 0, total: 6 }, expected_s: 60, at: 0 },
      { stage: 'summarize', progress: { done: 1, total: 6 }, expected_s: 60, at: 10 * S },
      { stage: 'summarize', progress: { done: 3, total: 6 }, expected_s: 60, at: 30 * S },
    ]
    expect(progressState(st, 0, 30 * S).remainingS).toBe(105)
  })

  it('요약 0/6이면 남은 시간을 추정하지 않는다', () => {
    const st: Stamped[] = [{ stage: 'summarize', progress: { done: 0, total: 6 }, at: 0 }]
    expect(progressState(st, 0, 5 * S)).toMatchObject({ percent: 10, remainingS: null })
  })

  it('요약이 캐시라 분석만 해도 분석 구간(75%~)으로 간다', () => {
    const st: Stamped[] = [{ stage: 'analyze', expected_s: 90, at: 0 }]
    expect(progressState(st, 0, 45 * S)).toEqual({ percent: 85, elapsedS: 45, remainingS: 45 })
  })

  it('예상 시간을 넘기면 95%에서 멈추고 남은 시간 0', () => {
    const st: Stamped[] = [{ stage: 'analyze', expected_s: 90, at: 0 }]
    expect(progressState(st, 0, 200 * S)).toMatchObject({ percent: 95, remainingS: 0 })
  })

  it('expected_s가 없으면 기본값', () => {
    const st: Stamped[] = [{ stage: 'analyze', at: 0 }]
    expect(progressState(st, 0, 0).remainingS).toBe(DEFAULT_ANALYZE_S)
  })

  it('formatDuration', () => {
    expect(formatDuration(45)).toBe('45초')
    expect(formatDuration(80)).toBe('1분 20초')
    expect(formatDuration(120)).toBe('2분')
  })
})

describe('AnalyzeProgress', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-16T00:00:00Z'))
  })
  afterEach(() => vi.useRealTimers())

  const analyzing = (expected: number): StreamEvent[] => [
    { type: 'status', stage: 'analyze', message: '분석 중', expected_s: expected, progress: null, cache: false, waiting: null },
  ]

  it('progressbar 역할과 현재 값, 경과·남은 시간', async () => {
    const w = mount(AnalyzeProgress, { props: { events: analyzing(90) } })
    await vi.advanceTimersByTimeAsync(45 * S)
    const bar = w.get('[role="progressbar"]')
    expect(bar.attributes('aria-valuenow')).toBe('85')
    expect(bar.attributes('aria-label')).toBe(copy.progress.label)
    expect(w.text()).toContain(copy.progress.elapsed('45초'))
    expect(w.text()).toContain(copy.progress.remaining(45))
    w.unmount()
  })

  it('예상 시간을 넘기면 "거의 다 됐어요"', async () => {
    const w = mount(AnalyzeProgress, { props: { events: analyzing(10) } })
    await vi.advanceTimersByTimeAsync(30 * S)
    expect(w.text()).toContain(copy.progress.almostDone)
    w.unmount()
  })

  it('기다리는 중이면 안내 문구, 막대는 뒤로 가지 않는다', async () => {
    const events: StreamEvent[] = [
      { type: 'status', stage: 'summarize', message: 'x', waiting: true, progress: null, cache: false, expected_s: 90 },
    ]
    const w = mount(AnalyzeProgress, { props: { events } })
    await vi.advanceTimersByTimeAsync(120 * S)
    expect(w.text()).toContain(copy.progress.waiting)
    expect(w.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('41')
    await w.setProps({
      events: [
        ...events,
        { type: 'status', stage: 'summarize', message: 'x', progress: { done: 1, total: 6 }, cache: false, expected_s: 90, waiting: null },
      ],
    })
    await vi.advanceTimersByTimeAsync(1 * S)
    expect(w.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('41')
    expect(w.text()).not.toContain(copy.progress.waiting)
    w.unmount()
  })

  it('남은 시간 문구: 1분 미만은 "1분 이내", 이상은 올림 분', () => {
    expect(copy.progress.remaining(30)).toBe('1분 이내 남음')
    expect(copy.progress.remaining(130)).toBe('약 3분 남음')
  })
})

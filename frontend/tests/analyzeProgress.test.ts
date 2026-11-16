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

  it('요약 3/6: 10 + 60×½ = 40%, 남은 시간 = 조각 속도 × 남은 조각 + 첫 조각 시간 + 분석 예상', () => {
    const st: Stamped[] = [
      { stage: 'files', at: 0 },
      { stage: 'summarize', progress: { done: 0, total: 6 }, at: 0 },
      { stage: 'summarize', progress: { done: 1, total: 6 }, at: 10 * S },
      { stage: 'summarize', progress: { done: 3, total: 6 }, at: 30 * S },
    ]
    expect(progressState(st, 0, 30 * S)).toEqual({ percent: 40, elapsedS: 30, remainingS: 130 })
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
    { type: 'status', stage: 'analyze', message: '분석 중', expected_s: expected, progress: null, cache: false },
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

  it('남은 시간 문구: 1분 미만은 "1분 이내", 이상은 올림 분', () => {
    expect(copy.progress.remaining(30)).toBe('1분 이내 남음')
    expect(copy.progress.remaining(130)).toBe('약 3분 남음')
  })
})

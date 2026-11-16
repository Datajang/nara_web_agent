// 분석 진행 로딩바 계산 (§7.5-4). 요약은 조각 진행률(done/total)로 실제 진행을,
// 분석은 LLM 한 번이라 서버가 준 예상 시간(expected_s) 동안 75→95%를 천천히 채운다.
// 남은 시간은 짧게 약속하지 않는다: 요약 중엔 분석 예상 시간까지 더하고, 넘기면 0(= '거의 다 됐어요').
import type { Stage } from '@/api/types'
import { copy } from '@/copy'

export interface Stamped {
  stage: Stage
  progress?: { done: number; total: number } | null
  expected_s?: number | null
  at: number // 받은 시각(ms)
}

export const DEFAULT_ANALYZE_S = 90

const FIXED: Partial<Record<Stage, number>> = { files: 5, extract: 10 }

export function progressState(
  stamped: Stamped[],
  startedAt: number,
  now: number,
): { percent: number; elapsedS: number; remainingS: number | null } {
  const elapsedS = Math.max(0, Math.floor((now - startedAt) / 1000))
  const last = stamped[stamped.length - 1]
  if (!last) return { percent: 0, elapsedS, remainingS: null }

  const analyze = stamped.find((s) => s.stage === 'analyze')
  if (analyze) {
    const expected = analyze.expected_s ?? DEFAULT_ANALYZE_S
    const e = (now - analyze.at) / 1000
    const percent = Math.floor(75 + 20 * Math.min(1, e / expected))
    return { percent, elapsedS, remainingS: Math.max(0, Math.round(expected - e)) }
  }

  if (last.stage === 'summarize') {
    const sums = stamped.filter((s) => s.stage === 'summarize')
    const p = [...sums].reverse().find((s) => s.progress)?.progress
    if (!p || p.total <= 0) return { percent: 10, elapsedS, remainingS: null }
    const percent = Math.floor(10 + (60 * p.done) / p.total)
    const firstDone = sums.find((s) => (s.progress?.done ?? 0) >= 1)
    if (p.done < 1 || !firstDone) return { percent, elapsedS, remainingS: null }
    const start = sums[0]!.at
    const perChunk = (now - start) / 1000 / p.done
    const firstChunkS = (firstDone.at - start) / 1000
    const remainingS = Math.round(perChunk * (p.total - p.done) + firstChunkS + DEFAULT_ANALYZE_S)
    return { percent, elapsedS, remainingS }
  }

  return { percent: FIXED[last.stage] ?? 0, elapsedS, remainingS: null }
}

export function formatDuration(s: number): string {
  return copy.progress.duration(Math.floor(s / 60), Math.floor(s % 60))
}

// 분석 진행 로딩바 계산 (§7.5-4). 요약은 조각 진행률(done/total)로 실제 진행을,
// 분석은 LLM 한 번이라 서버가 준 예상 시간(expected_s) 동안 75→95%를 천천히 채운다.
// 남은 시간은 짧게 약속하지 않는다: 요약 중엔 분석 예상 시간까지 더하고, 넘기면 0(= '거의 다 됐어요').
import type { Stage } from '@/api/types'
import { copy } from '@/copy'

export interface Stamped {
  stage: Stage
  progress?: { done: number; total: number } | null
  expected_s?: number | null
  waiting?: boolean | null
  at: number // 받은 시각(ms)
}

export const DEFAULT_ANALYZE_S = 90
// 조각을 다 읽은 뒤 합치기(reduce)는 첫 조각 시간의 1~1.5배 걸렸다(실측 b546·b565·b568, 2026-11-16)
const REDUCE_FACTOR = 1.5

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
    const start = sums[0]!.at
    const e = (now - start) / 1000
    const analyzeS = [...stamped].reverse().find((s) => s.expected_s)?.expected_s ?? DEFAULT_ANALYZE_S
    const p = [...sums].reverse().find((s) => s.progress)?.progress
    // 진행률이 없으면(다른 요청을 기다리는 중 등) 10→60%를 천천히, 남은 시간은 모름
    if (!p || p.total <= 0)
      return {
        percent: Math.floor(10 + 50 * (1 - Math.exp(-e / 120))),
        elapsedS,
        remainingS: null,
      }
    const firstDone = sums.find((s) => (s.progress?.done ?? 0) >= 1)
    if (p.done < 1 || !firstDone) {
      // 첫 조각을 읽는 중: 첫 칸 안에서만 천천히(다음 칸을 넘지 않음)
      const percent = Math.floor(10 + (60 / p.total) * 0.9 * (1 - Math.exp(-e / 60)))
      return { percent, elapsedS, remainingS: null }
    }
    const reduceS = ((firstDone.at - start) / 1000) * REDUCE_FACTOR
    if (p.done >= p.total) {
      // 합치는 중: 70→75%, 남은 시간은 줄어든다
      const lastAt = [...sums].reverse().find((s) => s.progress)!.at
      const r = (now - lastAt) / 1000
      const percent = Math.floor(70 + 5 * Math.min(1, reduceS > 0 ? r / reduceS : 1))
      return { percent, elapsedS, remainingS: Math.round(Math.max(0, reduceS - r) + analyzeS) }
    }
    const percent = Math.floor(10 + (60 * p.done) / p.total)
    const perChunk = e / p.done
    const remainingS = Math.round(perChunk * (p.total - p.done) + reduceS + analyzeS)
    return { percent, elapsedS, remainingS }
  }

  return { percent: FIXED[last.stage] ?? 0, elapsedS, remainingS: null }
}

export function formatDuration(s: number): string {
  return copy.progress.duration(Math.floor(s / 60), Math.floor(s % 60))
}

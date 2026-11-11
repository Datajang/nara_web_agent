// 색 의미 규칙 (SPEC §10.1). 색만으로 의미를 전달하지 않도록 배지에는 항상 텍스트가 붙는다.
import type { Tone } from '@/stores/ui'

const DAY_MS = 86_400_000
const KST_MS = 9 * 3_600_000

/** 마감: 8일 이상 neutral, 4~7일 warning, 3일 이내 danger, 마감 지남·미정 neutral. */
export function deadlineTone(deadlineIso: string | null | undefined, now: Date): Tone {
  if (!deadlineIso) return 'neutral'
  const d = new Date(deadlineIso)
  if (d.getTime() <= now.getTime()) return 'neutral'
  const days =
    Math.floor((d.getTime() + KST_MS) / DAY_MS) - Math.floor((now.getTime() + KST_MS) / DAY_MS)
  if (days <= 3) return 'danger'
  return days <= 7 ? 'warning' : 'neutral'
}

/** 적합도 점수: 80 이상 success, 60~79 primary, 60 미만 neutral(빨간색 안 씀). */
export function scoreTone(score: number): Tone {
  if (score >= 80) return 'success'
  return score >= 60 ? 'primary' : 'neutral'
}

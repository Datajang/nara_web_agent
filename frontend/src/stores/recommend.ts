// 맞춤 추천 상태 (SPEC §7.4). 다른 화면에 다녀와도 조건·진행·결과가 남도록 스토어에 둔다.
// 새로고침·다른 기기에서는 이 계정의 마지막 추천 기록(search_runs, kind=recommend)을 불러온다.
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { libraryApi } from '@/api/library'
import type { BidCard, SearchRunDetail, StreamEvent } from '@/api/types'
import { useSse } from '@/composables/useSse'

export const DAY_OPTIONS = [7, 14, 30] as const
export const CANDIDATE_OPTIONS = [20, 30, 40, 50] as const
export type Days = (typeof DAY_OPTIONS)[number]
export type CandidateCount = (typeof CANDIDATE_OPTIONS)[number]
export type Source = 'all' | 'regular' | 'prespec'

const SOURCES: readonly Source[] = ['all', 'regular', 'prespec']
const pick = <T>(options: readonly T[], value: unknown, fallback: T): T =>
  options.includes(value as T) ? (value as T) : fallback

export const useRecommendStore = defineStore('recommend', () => {
  const ownerId = ref<number | null>(null)
  const profileId = ref<number | null>(null)
  const days = ref<Days>(14)
  const source = ref<Source>('all')
  const candidates = ref<CandidateCount>(20)
  const keywords = ref<string[]>([])
  /** 1억 원 미만 사업도 후보에 넣을지(기본은 뺌) */
  const includeSmall = ref(false)
  const sse = useSse<StreamEvent>({ keepAlive: true })
  const cards = ref<BidCard[]>([])
  const ran = ref(false)
  /** 서버 기록에서 불러온 결과면 그 실행 시각 */
  const restoredAt = ref<string | null>(null)
  let restoreTried = false

  function reset(): void {
    sse.abort()
    sse.events.value = []
    sse.error.value = null
    profileId.value = null
    days.value = 14
    source.value = 'all'
    candidates.value = 20
    keywords.value = []
    includeSmall.value = false
    cards.value = []
    ran.value = false
    restoredAt.value = null
    restoreTried = false
  }

  function applyRun(r: SearchRunDetail): void {
    const q = r.query
    profileId.value = r.profile_id
    days.value = pick(DAY_OPTIONS, q.days, 14)
    source.value = pick(SOURCES, q.source, 'all')
    candidates.value = pick(CANDIDATE_OPTIONS, q.candidates_max, 20)
    const kws = Array.isArray(q.keywords) ? q.keywords.map(String) : []
    keywords.value = q.custom_keywords === true ? kws : []
    includeSmall.value = q.include_small === true
    cards.value = r.items
    ran.value = true
    restoredAt.value = r.created_at
  }

  /** 다른 계정의 상태면 비우고, 이 계정에서 처음 열면 마지막 추천 기록을 불러온다. */
  async function ensureFor(userId: number): Promise<void> {
    if (ownerId.value !== userId) {
      reset()
      ownerId.value = userId
    }
    if (restoreTried || ran.value) return
    restoreTried = true
    try {
      const last = (await libraryApi.runs('recommend', 1)).items[0]
      if (!last || ran.value) return
      const detail = await libraryApi.run(last.id, 0, CANDIDATE_OPTIONS[CANDIDATE_OPTIONS.length - 1])
      if (!ran.value && ownerId.value === userId) applyRun(detail)
    } catch {
      // 기록을 못 불러와도 새로 추천받으면 된다
    }
  }

  async function run(): Promise<void> {
    if (profileId.value === null) return
    ran.value = true
    restoredAt.value = null
    cards.value = []
    await sse.start('/recommend', {
      profile_id: profileId.value,
      days: days.value,
      source: source.value,
      candidates: candidates.value,
      top_n: candidates.value,
      include_small: includeSmall.value,
      keywords: keywords.value.length ? keywords.value : null,
    })
    const ev = sse.events.value.find((e) => e.type === 'cards')
    if (ev?.type === 'cards') cards.value = ev.items
  }

  return {
    ownerId,
    profileId,
    days,
    source,
    candidates,
    keywords,
    includeSmall,
    events: sse.events,
    stage: sse.stage,
    streaming: sse.streaming,
    error: sse.error,
    cards,
    ran,
    restoredAt,
    ensureFor,
    run,
    reset,
  }
})

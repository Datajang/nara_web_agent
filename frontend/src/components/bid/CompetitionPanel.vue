<script setup lang="ts">
// 공고 상세 '경쟁 구도' 탭 (§15.7). 탭을 열 때만 불러온다(참가 업체 점수가 온디맨드 G2B 호출이라).
// 같은 수요기관의 비슷한 과거 사업 낙찰, 낙찰률 분포(최소·중앙·최대), 참가 업체 점수, 우리 회사 참가 이력.
// 투찰 가격 추천·낙찰 예측은 보여 주지 않는다(§15.1 비목표).
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { competitorsApi, type Spread } from '@/api/competitors'
import AwardsBasis from '@/components/awards/AwardsBasis.vue'
import AwardsFootnote from '@/components/awards/AwardsFootnote.vue'
import CompetitionAwardItem from '@/components/bid/CompetitionAwardItem.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { copy } from '@/copy'
import { formatPct } from '@/utils/format'

const props = defineProps<{ bidId: string }>()
const q = useQuery({
  queryKey: computed(() => ['competition', props.bidId]),
  queryFn: () => competitorsApi.competition(props.bidId),
  staleTime: 60_000,
})
const c = computed(() => q.data.value)
const status = computed(() => c.value?.participants_status)

const spreads = computed(() => {
  const d = c.value?.distribution
  if (!d) return []
  const rows: Array<{ key: string; label: string; s: Spread | null | undefined; scale: number }> = [
    { key: 'g2b_rate', label: copy.competition.rateG2b, s: d.g2b_rate, scale: 1 },
    { key: 'award_ratio', label: copy.competition.ratio, s: d.award_ratio, scale: 100 },
  ]
  return rows.map((r) => ({
    ...r,
    cells: r.s
      ? [
          [copy.competition.spreadMin, `${formatPct(r.s.min * r.scale)}%`],
          [copy.competition.spreadMedian, `${formatPct(r.s.median * r.scale)}%`],
          [copy.competition.spreadMax, `${formatPct(r.s.max * r.scale)}%`],
        ]
      : [],
  }))
})
</script>

<template>
  <div class="flex flex-col gap-4" data-competition>
    <UiSkeleton v-if="q.isPending.value" :lines="4" />
    <div v-else-if="q.isError.value" class="flex items-center gap-3 text-danger-fg" role="alert">
      {{ copy.competition.loadFailed }}
      <UiButton size="sm" variant="secondary" @click="q.refetch()">{{ copy.common.retry }}</UiButton>
    </div>
    <template v-else-if="c">
      <header class="flex flex-col gap-2">
        <p class="text-sm text-text-2">{{ copy.competition.intro }}</p>
        <p v-if="c.org.name" class="font-medium">{{ copy.competition.org(c.org.name) }}</p>
        <p v-else class="text-text-3">{{ copy.competition.noOrg }}</p>
        <AwardsBasis :period="c.period" />
      </header>

      <p
        v-if="status && (status.partial || status.failed)"
        class="rounded-card border border-warning-fg/30 bg-warning-bg px-4 py-3 text-sm text-warning-fg"
        role="note"
        data-partial
      >
        <template v-if="status.failed">{{ copy.competition.fetchFailed }}</template>
        <template v-else>
          {{ copy.competition.partial(status.loaded, status.requested) }}
          <template v-if="status.budget_exhausted"> {{ copy.competition.budget }}</template>
        </template>
      </p>

      <div class="grid gap-4 lg:grid-cols-2">
        <section class="rounded-card border border-border bg-surface p-4" :aria-label="copy.competition.distribution" data-distribution>
          <h3 class="mb-1 text-lg font-semibold">{{ copy.competition.distribution }}</h3>
          <p class="mb-3 text-xs text-text-3">{{ copy.competition.distributionNote(c.distribution.basis) }}</p>
          <dl class="flex flex-col gap-3">
            <div v-for="r in spreads" :key="r.key" :data-spread="r.key">
              <dt class="text-sm text-text-2">
                {{ r.label }}
                <span v-if="r.s" class="text-xs text-text-3">· {{ copy.competition.spreadCount(r.s.n) }}</span>
              </dt>
              <dd v-if="r.s" class="mt-1 grid grid-cols-3 gap-2">
                <span v-for="[label, value] in r.cells" :key="label" class="rounded-control bg-surface-2 px-2 py-1.5">
                  <span class="block text-xs text-text-3">{{ label }}</span>
                  <span class="text-base font-semibold tabular">{{ value }}</span>
                </span>
              </dd>
              <dd v-else class="mt-1 text-sm text-text-3">{{ copy.competition.noSpread }}</dd>
            </div>
          </dl>
        </section>
        <section class="rounded-card border border-border bg-surface p-4" :aria-label="copy.competition.usTitle" data-us-history>
          <h3 class="mb-2 text-lg font-semibold">{{ copy.competition.usTitle }}</h3>
          <p v-if="c.us" class="text-sm tabular text-text-2">
            {{ copy.competition.usLine(c.us.org_awards, c.us.participated, c.us.won) }}
          </p>
          <p v-else class="text-sm text-text-3">{{ copy.competition.usNotConfigured }}</p>
          <p class="mt-2 text-xs text-text-3">{{ copy.competitors.h2hNote }}</p>
        </section>
      </div>

      <section v-if="c.this_award" class="rounded-card border border-border bg-surface p-4" :aria-label="copy.competition.thisAward" data-this-award>
        <h3 class="text-lg font-semibold">{{ copy.competition.thisAward }}</h3>
        <CompetitionAwardItem :award="c.this_award" :us-bizno="c.us?.bizno ?? null" open />
      </section>

      <section class="rounded-card border border-border bg-surface p-4" :aria-label="copy.competition.similar" data-similar>
        <div class="flex flex-wrap items-baseline gap-2">
          <h3 class="text-lg font-semibold">{{ copy.competition.similar }}</h3>
          <span v-if="c.similar.length" class="text-sm text-text-3 tabular">
            {{ copy.competition.similarCount(c.similar.length, c.similar_total) }}
          </span>
        </div>
        <p v-if="!c.similar.length" class="py-4 text-text-3">{{ copy.competition.noSimilar }}</p>
        <CompetitionAwardItem v-for="a in c.similar" :key="`${a.bid_ntce_no}-${a.bid_ntce_ord}`" :award="a" :us-bizno="c.us?.bizno ?? null" />
      </section>
      <AwardsFootnote />
    </template>
  </div>
</template>

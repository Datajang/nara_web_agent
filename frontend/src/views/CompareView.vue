<script setup lang="ts">
// 우리 회사와 경쟁사 비교 (§15.7 /competitors/:bizno). 맨 위에 강점·약점 카드와 항목별 판정 표,
// 이어서 한눈에 보기, 연도별 낙찰, 수요기관 겹침, 주력 분야, 공동수급 파트너, 경쟁사 최근 낙찰, AI 해설.
// 판정은 서버가 규칙(§15.5)으로 계산한 값 그대로다. LLM은 쓰지 않는다(AI 해설은 P11).
import { useQuery } from '@tanstack/vue-query'
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { awardsApi, formatBizno } from '@/api/awards'
import { ApiError } from '@/api/client'
import { competitorsApi, type VerdictRow } from '@/api/competitors'
import AwardsBasis from '@/components/awards/AwardsBasis.vue'
import AwardsFootnote from '@/components/awards/AwardsFootnote.vue'
import AwardTable from '@/components/awards/AwardTable.vue'
import PairBars from '@/components/awards/PairBars.vue'
import type { PairRow } from '@/components/awards/pair'
import VerdictBadge from '@/components/awards/VerdictBadge.vue'
import WatchButton from '@/components/awards/WatchButton.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { copy } from '@/copy'
import { formatMoney, formatPct } from '@/utils/format'

const route = useRoute()
const bizno = computed(() => String(route.params.bizno ?? ''))
const cmp = useQuery({
  queryKey: computed(() => ['competitors', 'compare', bizno.value]),
  queryFn: () => competitorsApi.compare(bizno.value),
})
const themSummary = useQuery({
  queryKey: computed(() => ['company', bizno.value]),
  queryFn: () => awardsApi.companySummary(bizno.value),
})
const errorText = computed(() => {
  const e = cmp.error.value
  if (e instanceof ApiError && e.code === 'not_configured') return copy.awards.notConfiguredBody
  if (e instanceof ApiError && e.status === 400) return copy.competitors.sameCompany
  return copy.competitors.loadFailed
})
const watched = ref<boolean | null>(null)
const isWatched = computed(() => watched.value ?? cmp.data.value?.watched ?? false)

const MONEY = new Set(['amount_sum', 'amount_avg'])
const PCT = new Set(['ratio_median', 'joint_share']) // 0~1 → %
function valueText(r: VerdictRow, v: number | null | undefined): string {
  if (v === null || v === undefined) return copy.competitors.noValue
  if (MONEY.has(r.key)) return formatMoney(v)
  if (PCT.has(r.key)) return `${formatPct(v * 100)}%`
  if (r.key === 'g2b_rate_median') return `${formatPct(v)}%`
  if (r.key === 'org_count') return copy.awards.orgUnit(v)
  return copy.awards.countUnit(v)
}
function ruleText(r: VerdictRow): string {
  if (r.rule === 'head_to_head' && cmp.data.value) return copy.competitors.h2hRule(cmp.data.value.head_to_head.matched)
  return copy.competitors.rules[r.rule]
}

const byKey = computed(() => new Map((cmp.data.value?.verdicts ?? []).map((v) => [v.key, v])))
const cards = (keys: string[]) => keys.map((k) => byKey.value.get(k)).filter((v): v is VerdictRow => !!v)
const strengths = computed(() => cards(cmp.data.value?.strengths ?? []))
const weaknesses = computed(() => cards(cmp.data.value?.weaknesses ?? []))
const fieldRows = computed(() => (cmp.data.value?.verdicts ?? []).filter((v) => v.rule === 'field_2x'))

const overview = computed<PairRow[]>(() =>
  ['count', 'amount_sum', 'amount_avg', 'org_count']
    .map((k) => byKey.value.get(k))
    .filter((v): v is VerdictRow => !!v)
    .map((v) => ({
      key: v.key,
      label: v.label,
      us: v.us ?? null,
      them: v.them ?? null,
      usText: valueText(v, v.us),
      themText: valueText(v, v.them),
    })),
)
const years = computed<PairRow[]>(() =>
  [...(cmp.data.value?.by_year ?? [])].reverse().map((y) => ({
    key: y.year,
    label: copy.awards.yearLabel(y.year),
    us: y.us ?? null,
    them: y.them ?? null,
    usText: y.us === null || y.us === undefined ? '' : copy.awards.countUnit(y.us),
    themText: y.them === null || y.them === undefined ? '' : copy.awards.countUnit(y.them),
    collecting: y.collecting,
  })),
)
const field = ref('')
const org = ref('')
</script>

<template>
  <div class="flex flex-col gap-4">
    <UiSkeleton v-if="cmp.isPending.value" :lines="4" />
    <div v-else-if="cmp.isError.value" class="flex items-center gap-3 text-danger-fg" role="alert">
      {{ errorText }}
      <UiButton size="sm" variant="secondary" @click="cmp.refetch()">{{ copy.common.retry }}</UiButton>
    </div>
    <template v-else-if="cmp.data.value">
      <header class="flex flex-col gap-2">
        <div class="flex flex-wrap items-center gap-3">
          <p class="text-lg font-semibold">
            {{ cmp.data.value.us.name }}
            <span class="mx-1 text-text-3">{{ copy.competitors.vs }}</span>
            {{ cmp.data.value.them.name }}
            <span class="ml-2 text-sm font-normal text-text-2 tabular">{{ formatBizno(cmp.data.value.them.bizno) }}</span>
          </p>
          <WatchButton class="ml-auto" :bizno="cmp.data.value.them.bizno" :watched="isWatched" @changed="watched = $event" />
        </div>
        <p v-if="cmp.data.value.period.counted_from && cmp.data.value.period.counted_to" class="text-sm text-text-2 tabular">
          {{ copy.competitors.periodNote(cmp.data.value.period.counted_from, cmp.data.value.period.counted_to) }}
        </p>
        <AwardsBasis :period="cmp.data.value.period" />
      </header>

      <div class="grid gap-4 md:grid-cols-2">
        <section class="rounded-card border border-border bg-surface p-4" :aria-label="copy.competitors.strengths" data-strengths>
          <h3 class="mb-3 text-lg font-semibold">{{ copy.competitors.strengths }}</h3>
          <p v-if="!strengths.length" class="text-text-3">{{ copy.competitors.noStrengths }}</p>
          <ul v-else class="flex flex-col gap-2">
            <li v-for="v in strengths" :key="v.key" class="flex flex-wrap items-center gap-2 text-sm">
              <VerdictBadge :verdict="v.verdict" :small-sample="v.small_sample" />
              <span class="font-medium">{{ v.label }}</span>
              <span class="tabular text-text-2">{{ copy.competitors.cardLine(valueText(v, v.us), valueText(v, v.them)) }}</span>
            </li>
          </ul>
        </section>
        <section class="rounded-card border border-border bg-surface p-4" :aria-label="copy.competitors.weaknesses" data-weaknesses>
          <h3 class="mb-3 text-lg font-semibold">{{ copy.competitors.weaknesses }}</h3>
          <p v-if="!weaknesses.length" class="text-text-3">{{ copy.competitors.noWeaknesses }}</p>
          <ul v-else class="flex flex-col gap-2">
            <li v-for="v in weaknesses" :key="v.key" class="flex flex-wrap items-center gap-2 text-sm">
              <VerdictBadge :verdict="v.verdict" :small-sample="v.small_sample" />
              <span class="font-medium">{{ v.label }}</span>
              <span class="tabular text-text-2">{{ copy.competitors.cardLine(valueText(v, v.us), valueText(v, v.them)) }}</span>
            </li>
          </ul>
        </section>
      </div>

      <section class="rounded-card border border-border bg-surface p-4" :aria-label="copy.competitors.verdictTable">
        <h3 class="mb-3 text-lg font-semibold">{{ copy.competitors.verdictTable }}</h3>
        <div class="overflow-x-auto">
          <table class="w-full min-w-[640px] text-sm" data-verdicts>
            <thead class="bg-surface-2 text-left text-text-2">
              <tr>
                <th scope="col" class="px-3 py-2">{{ copy.competitors.colItem }}</th>
                <th scope="col" class="px-3 py-2 text-right">{{ copy.competitors.colUs }}</th>
                <th scope="col" class="px-3 py-2 text-right">{{ copy.competitors.colThem }}</th>
                <th scope="col" class="px-3 py-2">{{ copy.competitors.colVerdict }}</th>
                <th scope="col" class="px-3 py-2">{{ copy.competitors.colRule }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="v in cmp.data.value.verdicts" :key="v.key" class="border-t border-border" :data-row="v.key">
                <th scope="row" class="px-3 py-2 text-left font-medium">{{ v.label }}</th>
                <td class="px-3 py-2 text-right tabular">{{ valueText(v, v.us) }}</td>
                <td class="px-3 py-2 text-right tabular">{{ valueText(v, v.them) }}</td>
                <td class="px-3 py-2"><VerdictBadge :verdict="v.verdict" :small-sample="v.small_sample" /></td>
                <td class="px-3 py-2 text-text-2">{{ ruleText(v) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="mt-2 text-xs text-text-3">{{ copy.competitors.h2hNote }}</p>
      </section>

      <div class="grid gap-4 lg:grid-cols-2">
        <section class="rounded-card border border-border bg-surface p-4" :aria-label="copy.competitors.overview">
          <h3 class="mb-3 text-lg font-semibold">{{ copy.competitors.overview }}</h3>
          <PairBars :rows="overview" scale="row" :us-name="cmp.data.value.us.name" :them-name="cmp.data.value.them.name" />
        </section>
        <section class="rounded-card border border-border bg-surface p-4" :aria-label="copy.competitors.byYear">
          <h3 class="mb-3 text-lg font-semibold">{{ copy.competitors.byYear }}</h3>
          <PairBars :rows="years" :us-name="cmp.data.value.us.name" :them-name="cmp.data.value.them.name" />
        </section>
      </div>

      <div class="grid gap-4 lg:grid-cols-2">
        <section class="rounded-card border border-border bg-surface p-4" :aria-label="copy.competitors.sharedOrgs">
          <h3 class="mb-3 text-lg font-semibold">{{ copy.competitors.sharedOrgs }}</h3>
          <p v-if="!cmp.data.value.shared_orgs.length" class="text-text-3">{{ copy.competitors.noSharedOrgs }}</p>
          <table v-else class="w-full text-sm" data-shared-orgs>
            <thead class="text-left text-text-2">
              <tr>
                <th scope="col" class="py-1">{{ copy.awards.colOrg }}</th>
                <th scope="col" class="py-1 text-right">{{ copy.competitors.colUs }}</th>
                <th scope="col" class="py-1 text-right">{{ copy.competitors.colThem }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="o in cmp.data.value.shared_orgs" :key="o.dminstt_cd" class="border-t border-border">
                <td class="py-1.5">{{ o.dminstt_name ?? o.dminstt_cd }}</td>
                <td class="py-1.5 text-right tabular">{{ copy.awards.countUnit(o.us) }}</td>
                <td class="py-1.5 text-right tabular">{{ copy.awards.countUnit(o.them) }}</td>
              </tr>
            </tbody>
          </table>
        </section>
        <section class="rounded-card border border-border bg-surface p-4" :aria-label="copy.competitors.fields">
          <h3 class="mb-3 text-lg font-semibold">{{ copy.competitors.fields }}</h3>
          <p v-if="!fieldRows.length" class="text-text-3">{{ copy.competitors.noFields }}</p>
          <ul v-else class="flex flex-col gap-2">
            <li v-for="f in fieldRows" :key="f.key" class="flex flex-wrap items-center gap-2 text-sm">
              <span class="min-w-24 font-medium">{{ f.label }}</span>
              <span class="tabular text-text-2">{{ copy.competitors.cardLine(valueText(f, f.us), valueText(f, f.them)) }}</span>
              <VerdictBadge :verdict="f.verdict" :small-sample="f.small_sample" />
            </li>
          </ul>
        </section>
      </div>

      <section class="rounded-card border border-border bg-surface p-4" :aria-label="copy.competitors.jointPartners">
        <h3 class="mb-2 text-lg font-semibold">{{ copy.competitors.jointPartners }}</h3>
        <p class="text-text-3">{{ copy.competitors.jointPending }}</p>
      </section>

      <div class="flex flex-col gap-2">
        <h3 class="text-lg font-semibold">{{ copy.competitors.recentAwards }}</h3>
        <UiSkeleton v-if="themSummary.isPending.value" :lines="2" />
        <AwardTable
          v-else-if="themSummary.data.value"
          v-model:field="field"
          v-model:org="org"
          :summary="themSummary.data.value"
          :bizno="cmp.data.value.them.bizno"
        />
      </div>

      <section class="rounded-card border border-border bg-surface p-4" :aria-label="copy.competitors.aiExplain" data-ai-explain>
        <h3 class="mb-2 text-lg font-semibold">{{ copy.competitors.aiExplain }}</h3>
        <p class="text-text-3">{{ copy.competitors.aiPending }}</p>
      </section>
      <AwardsFootnote />
    </template>
  </div>
</template>

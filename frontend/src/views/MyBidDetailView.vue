<script setup lang="ts">
// 투찰 결과 상세 (P12): 우리 결과(순위·투찰·점수 또는 탈락 사유), 낙찰 업체, 참가 업체 전체.
// 경쟁사마다 비교 화면으로 간다. 순위가 없는 업체는 부적격·탈락이고 사유는 비고에 있다(추정하지 않음).
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ApiError } from '@/api/client'
import { myBidsApi, rankText, resultBadge } from '@/api/mybids'
import AwardsFootnote from '@/components/awards/AwardsFootnote.vue'
import MoneyText from '@/components/bid/MoneyText.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { copy } from '@/copy'
import { formatDate, formatMoney, formatPct } from '@/utils/format'

const route = useRoute()
const key = computed(() => ({
  bid_ntce_no: String(route.params.no),
  bid_ntce_ord: String(route.params.ord),
  bid_clsfc_no: String(route.params.clsfc),
  rbid_no: String(route.params.rbid),
}))
const q = useQuery({
  queryKey: computed(() => ['my-bid', key.value]),
  queryFn: () => myBidsApi.detail(key.value),
})
const d = computed(() => q.data.value)
const notFound = computed(() => q.error.value instanceof ApiError && q.error.value.status === 404)
const item = computed(() => d.value?.item)
const score = (v: number | null | undefined) => (v == null ? '–' : v.toFixed(2))
const pct = (v: number | null | undefined) => (v == null ? '–' : `${formatPct(v)}%`)
const missingText = computed(() =>
  d.value?.budget_exhausted ? copy.myBids.budget : d.value?.failed ? copy.myBids.fetchFailed : copy.myBids.notLoaded,
)
</script>

<template>
  <div class="flex flex-col gap-4">
    <RouterLink to="/my-awards?tab=bids" class="text-sm text-primary hover:underline">← {{ copy.myBids.back }}</RouterLink>
    <UiSkeleton v-if="q.isPending.value" :lines="5" />
    <EmptyState v-else-if="notFound" :title="copy.myBids.notFound" />
    <p v-else-if="q.isError.value" class="flex items-center gap-3 text-danger-fg" role="alert">
      {{ copy.myBids.detailFailed }}
      <UiButton size="sm" variant="secondary" @click="q.refetch()">{{ copy.common.retry }}</UiButton>
    </p>
    <template v-else-if="d && item">
      <header class="flex flex-col gap-1">
        <h1 class="text-xl font-semibold">{{ item.title }}</h1>
        <p class="text-sm text-text-2">
          {{ item.dminstt_name }} · <span class="tabular">{{ item.bid_ntce_no }}</span> · {{ formatDate(item.registered_at) }}
          <RouterLink v-if="item.bid_id" :to="`/bids/${item.bid_id}`" class="ml-2 text-primary hover:underline">{{ copy.myBids.openBid }}</RouterLink>
        </p>
        <p><UiBadge tone="primary">{{ copy.awards.basis }}</UiBadge></p>
      </header>

      <div class="grid gap-3 sm:grid-cols-2">
        <section class="rounded-card border border-border bg-surface p-4" data-our-result>
          <h2 class="mb-2 font-semibold">{{ copy.myBids.ourResult }}</h2>
          <p class="flex items-center gap-2">
            <UiBadge size="md" :tone="resultBadge(item).tone">{{ resultBadge(item).label }}</UiBadge>
            <span class="tabular">{{ rankText(item) }}</span>
          </p>
          <dl class="mt-3 grid grid-cols-3 gap-2 text-sm">
            <div><dt class="text-text-3">{{ copy.myBids.ourBid }}</dt><dd><MoneyText :value="item.our_bid_amount" /></dd></div>
            <div><dt class="text-text-3">{{ copy.myBids.ourRate }}</dt><dd class="tabular">{{ pct(item.our_bid_rate) }}</dd></div>
            <div><dt class="text-text-3">{{ copy.myBids.ourScore }}</dt><dd class="tabular">{{ score(item.our_total_score) }}</dd></div>
          </dl>
        </section>
        <section class="rounded-card border border-border bg-surface p-4" data-winner>
          <h2 class="mb-2 font-semibold">{{ copy.myBids.winnerTitle }}</h2>
          <p>
            <RouterLink v-if="item.winner_bizno && item.result !== 'won'" :to="`/competitors/${item.winner_bizno}`" class="text-primary hover:underline">
              {{ item.winner_name ?? item.winner_bizno }}
            </RouterLink>
            <span v-else>{{ item.winner_name }}</span>
          </p>
          <dl class="mt-3 grid grid-cols-3 gap-2 text-sm">
            <div><dt class="text-text-3">{{ copy.myBids.awardAmount }}</dt><dd><MoneyText :value="item.award_amount" /></dd></div>
            <div><dt class="text-text-3">{{ copy.myBids.estimated }}</dt><dd><MoneyText :value="d.estimated_price" /></dd></div>
            <div><dt class="text-text-3">{{ copy.myBids.g2bRate }}</dt><dd class="tabular">{{ pct(d.g2b_award_rate) }}</dd></div>
          </dl>
        </section>
      </div>

      <section class="rounded-card border border-border bg-surface p-4">
        <p v-if="d.participants === null" class="text-text-2" role="status">{{ missingText }}</p>
        <p v-else-if="!d.participants.length" class="text-text-2">{{ copy.myBids.noParticipants }}</p>
        <template v-else>
          <h2 class="font-semibold">{{ copy.myBids.participantsTitle(d.participants.length) }}</h2>
          <p class="mb-2 text-xs text-text-3">{{ copy.myBids.rankHelp }}</p>
          <div class="overflow-x-auto">
            <table class="w-full min-w-[760px] text-sm" data-participants>
              <thead class="bg-surface-2 text-left text-text-2">
                <tr>
                  <th scope="col" class="w-14 px-2 py-1.5 text-right">{{ copy.myBids.colRank }}</th>
                  <th scope="col" class="px-2 py-1.5">{{ copy.myBids.colCompany }}</th>
                  <th scope="col" class="px-2 py-1.5 text-right">{{ copy.myBids.colBid }}</th>
                  <th scope="col" class="px-2 py-1.5 text-right">{{ copy.myBids.colRate }}</th>
                  <th scope="col" class="px-2 py-1.5 text-right">{{ copy.myBids.colTotal }}</th>
                  <th scope="col" class="px-2 py-1.5">{{ copy.myBids.colRemark }}</th>
                  <th scope="col" class="px-2 py-1.5 text-right">{{ copy.myBids.colAwards }}</th>
                  <th scope="col" class="px-2 py-1.5"><span class="sr-only">{{ copy.myBids.compare }}</span></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="p in d.participants"
                  :key="p.bizno"
                  class="border-t border-border"
                  :class="{ 'bg-primary-soft': p.is_us }"
                  :data-us="p.is_us || undefined"
                >
                  <td class="px-2 py-1.5 text-right tabular">{{ p.rank ?? '–' }}</td>
                  <td class="px-2 py-1.5">
                    {{ p.name ?? p.bizno }}
                    <UiBadge v-if="p.is_winner" tone="success" class="ml-1">{{ copy.myBids.winner }}</UiBadge>
                    <UiBadge v-if="p.is_us" tone="primary" class="ml-1">{{ copy.myBids.us }}</UiBadge>
                  </td>
                  <td class="px-2 py-1.5 text-right tabular">{{ formatMoney(p.bid_amount) }}</td>
                  <td class="px-2 py-1.5 text-right tabular">{{ pct(p.bid_rate) }}</td>
                  <td class="px-2 py-1.5 text-right tabular">{{ score(p.total_score) }}</td>
                  <td class="px-2 py-1.5 text-text-2" :class="{ 'text-warning-fg': p.rank == null }">{{ p.remark ?? '' }}</td>
                  <td class="px-2 py-1.5 text-right tabular">{{ copy.myBids.awardsCount(p.award_count) }}</td>
                  <td class="px-2 py-1.5">
                    <RouterLink v-if="!p.is_us" :to="`/competitors/${p.bizno}`" class="text-primary hover:underline">{{ copy.myBids.compare }}</RouterLink>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </section>
      <AwardsFootnote />
    </template>
  </div>
</template>

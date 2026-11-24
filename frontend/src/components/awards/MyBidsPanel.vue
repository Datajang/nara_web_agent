<script setup lang="ts">
// 우리 투찰 결과 (P12): 낙찰·탈락 목록. 결과 구분(전체·낙찰·탈락)은 URL ?result=와 맞춘다.
// 순위가 없으면 추정하지 않고 사유(비고)를 보여 준다 (docs/decisions/2026-11-17-p12a-opening-ranks.md).
// 연도·기간·사업명 필터(2026-11-24): 결과별 건수도 같은 조건으로 센다.
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { NO_NARROW, type AwardNarrow } from '@/api/awards'
import { keyPath, myBidsApi, rankText, resultBadge, type MyBid, type MyBidFilter, type MyBidList } from '@/api/mybids'
import AwardsFilter from '@/components/awards/AwardsFilter.vue'
import MoneyText from '@/components/bid/MoneyText.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiFilterBar from '@/components/ui/UiFilterBar.vue'
import UiSegmented from '@/components/ui/UiSegmented.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { copy } from '@/copy'
import { formatDate, formatPct } from '@/utils/format'

defineProps<{ years: number[] }>()
const route = useRoute()
const router = useRouter()
const narrow = ref<AwardNarrow>({ ...NO_NARROW })
const FILTERS: MyBidFilter[] = ['all', 'won', 'lost']
const filter = computed<MyBidFilter>({
  get: () => FILTERS.find((f) => f === route.query.result) ?? 'all',
  set: (v) => void router.replace({ query: { ...route.query, result: v === 'all' ? undefined : v } }),
})

const items = ref<MyBid[]>([])
const head = ref<Pick<MyBidList, 'counts' | 'scan'> | null>(null)
const cursor = ref<string | null>(null)
const loading = ref(false)
const failed = ref(false)

const options = computed(() => {
  const c = head.value?.counts
  return [
    { value: 'all' as const, label: copy.myBids.filterAll(c?.all ?? 0) },
    { value: 'won' as const, label: copy.myBids.filterWon(c?.won ?? 0) },
    { value: 'lost' as const, label: copy.myBids.filterLost(c?.lost ?? 0) },
  ]
})
const scanText = computed(() => {
  const sc = head.value?.scan
  if (!sc) return ''
  return sc.since ? copy.myBids.scan(formatDate(sc.since), sc.fetched_notices, sc.award_notices) : copy.myBids.scanNone
})
const emptyText = computed(() =>
  narrow.value.from || narrow.value.to || narrow.value.q
    ? copy.myBids.emptyFiltered
    : { all: copy.myBids.emptyAll, won: copy.myBids.emptyWon, lost: copy.myBids.emptyLost }[filter.value],
)

async function load(reset: boolean) {
  loading.value = true
  failed.value = false
  try {
    const page = await myBidsApi.list(filter.value, narrow.value, reset ? null : cursor.value)
    items.value = reset ? page.items : [...items.value, ...page.items]
    head.value = { counts: page.counts, scan: page.scan }
    cursor.value = page.next_cursor ?? null
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

watch([filter, narrow], () => load(true), { immediate: true })

const keyOf = (b: MyBid) => keyPath(b)
// 공동수급 역할·지분(2026-11-24): 구성원 낙찰도 '낙찰'로 센다
const roleText = (b: MyBid) => {
  const share = b.our_share != null ? formatPct(b.our_share) : null
  return b.our_role === 'member' ? copy.awards.roleMember(share) : copy.awards.roleLead(share ?? '')
}
</script>

<template>
  <section class="flex flex-col gap-3" :aria-label="copy.myBids.tabBids">
    <p class="text-sm text-text-2">{{ copy.myBids.intro }}</p>
    <UiFilterBar :label="copy.myBids.filterLabel">
      <UiSegmented v-model="filter" :label="copy.myBids.filterLabel" :options="options" hide-label />
      <template v-if="scanText" #end>
        <p class="text-xs text-text-3" data-scan>{{ scanText }}</p>
      </template>
    </UiFilterBar>
    <AwardsFilter v-model="narrow" :years="years" />

    <p v-if="failed" class="flex items-center gap-3 text-danger-fg" role="alert">
      {{ copy.myBids.loadFailed }}
      <UiButton size="sm" variant="secondary" @click="load(items.length === 0)">{{ copy.common.retry }}</UiButton>
    </p>
    <UiSkeleton v-else-if="loading && !items.length" :lines="4" />
    <p v-else-if="!items.length" class="py-6 text-center text-text-3">{{ emptyText }}</p>
    <div v-else class="overflow-x-auto rounded-card border border-border bg-surface">
      <table class="w-full min-w-[820px] text-sm" data-my-bids>
        <thead class="bg-surface-2 text-left text-xs font-semibold text-text-3">
          <tr>
            <th scope="col" class="px-3 py-2">{{ copy.myBids.colDate }}</th>
            <th scope="col" class="px-3 py-2">{{ copy.myBids.colTitle }}</th>
            <th scope="col" class="px-3 py-2">{{ copy.myBids.colResult }}</th>
            <th scope="col" class="px-3 py-2 text-right">{{ copy.myBids.colOurBid }}</th>
            <th scope="col" class="px-3 py-2">{{ copy.myBids.colWinner }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in items" :key="keyOf(b)" class="border-t border-border align-top" :data-my-bid="b.bid_ntce_no">
            <td class="whitespace-nowrap px-3 py-2 tabular">{{ formatDate(b.registered_at) }}</td>
            <td class="px-3 py-2">
              <RouterLink :to="`/my-awards/bids/${keyOf(b)}`" class="text-primary hover:underline">{{ b.title }}</RouterLink>
              <span class="mt-0.5 block text-xs text-text-3">{{ b.dminstt_name }}</span>
            </td>
            <td class="px-3 py-2">
              <UiBadge :tone="resultBadge(b).tone">{{ resultBadge(b).label }}</UiBadge>
              <span class="mt-0.5 block text-xs text-text-2 tabular" data-rank>{{ rankText(b) }}</span>
              <span v-if="b.our_role" class="mt-0.5 block text-xs text-primary-hover">{{ roleText(b) }}</span>
            </td>
            <td class="whitespace-nowrap px-3 py-2 text-right">
              <!-- 구성원은 직접 투찰하지 않았다: 투찰금액 대신 우리 지분 금액 -->
              <span v-if="b.our_role === 'member'" class="text-text-2" data-our-share-amount>
                {{ copy.awards.ourShare }}
                <MoneyText :value="b.our_share != null && b.award_amount ? Math.round((b.award_amount * b.our_share) / 100) : null" />
              </span>
              <MoneyText v-else :value="b.our_bid_amount" />
              <span v-if="b.our_bid_rate != null && b.our_role !== 'member'" class="block text-xs text-text-3 tabular">{{ formatPct(b.our_bid_rate) }}%</span>
            </td>
            <td class="px-3 py-2">
              <template v-if="b.our_role === 'member'">
                <RouterLink v-if="b.winner_bizno" :to="`/competitors/${b.winner_bizno}`" class="text-primary hover:underline">
                  {{ copy.awards.leadBy(b.winner_name ?? b.winner_bizno) }}
                </RouterLink>
                <span v-else>{{ copy.awards.leadBy(b.winner_name ?? '') }}</span>
                <span class="block text-xs"><MoneyText :value="b.award_amount" /></span>
              </template>
              <span v-else-if="b.result === 'won'" class="text-text-3">{{ copy.myBids.us }}</span>
              <template v-else>
                <RouterLink v-if="b.winner_bizno" :to="`/competitors/${b.winner_bizno}`" class="text-primary hover:underline">
                  {{ b.winner_name ?? b.winner_bizno }}
                </RouterLink>
                <span v-else>{{ b.winner_name }}</span>
                <span class="block text-xs"><MoneyText :value="b.award_amount" /></span>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="cursor && !failed" class="flex justify-center">
      <UiButton variant="secondary" :loading="loading" @click="load(false)">{{ copy.myBids.loadMore }}</UiButton>
    </div>
  </section>
</template>

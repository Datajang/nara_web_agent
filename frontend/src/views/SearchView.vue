<script setup lang="ts">
// 공고 검색 (SPEC §7.3). 조건은 URL과 동기화하고, 결과는 DB-first 검색(§6.3)의 스냅샷을 쓴다.
// 2026-11-18 넓은 화면 개편: 접는 큰 폼 대신 두 줄 조건 카드, 정렬은 결과 머리에서 바로 바꾼다.
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { bidsApi } from '@/api/bids'
import { libraryApi } from '@/api/library'
import type { BidCard, SearchResult } from '@/api/types'
import BidList from '@/components/bid/BidList.vue'
import DataAsOfBadge from '@/components/bid/DataAsOfBadge.vue'
import ChipInput from '@/components/ui/ChipInput.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import ExportButton from '@/components/bid/ExportButton.vue'
import UiSegmented from '@/components/ui/UiSegmented.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import {
  defaultState,
  fromRunQuery,
  parseSearch,
  PERIODS,
  toQuery,
  toRequest,
  type Period,
  type SearchState,
} from '@/composables/useUrlState'
import { copy } from '@/copy'
import { useBookmarkToggle } from '@/composables/useBookmarkToggle'

const COLLECTING_RETRY_MS = 4000
const COLLECTING_MAX_RETRIES = 5

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()
const form = ref<SearchState>(parseSearch(route.query))
const chips = ref<InstanceType<typeof ChipInput> | null>(null)
const result = ref<SearchResult | null>(null)
const items = ref<BidCard[]>([])
const loading = ref(false)
const loadingMore = ref(false)
const failed = ref(false)
let retryTimer: ReturnType<typeof setTimeout> | null = null
let collectingRetries = 0

const recent = useQuery({
  queryKey: ['search-runs', 'search', 5],
  queryFn: () => libraryApi.runs('search', 5),
})

const periodOptions = computed(() => [
  ...PERIODS.map((d) => ({ value: d as Period, label: copy.search.recentDays(d) })),
  { value: 'custom' as Period, label: copy.search.custom },
])

async function run(state: SearchState, fromRetry = false) {
  if (retryTimer) clearTimeout(retryTimer)
  if (!fromRetry) collectingRetries = 0
  loading.value = !fromRetry
  failed.value = false
  try {
    const res = await bidsApi.search(toRequest(state))
    result.value = res
    items.value = res.items
    void queryClient.invalidateQueries({ queryKey: ['search-runs'] })
    if (res.collecting && collectingRetries < COLLECTING_MAX_RETRIES) {
      collectingRetries++
      retryTimer = setTimeout(() => void run(state, true), COLLECTING_RETRY_MS)
    }
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

// URL이 바뀌면(새로고침·뒤로 가기·공유 링크 포함) 조건을 복원하고 검색한다.
watch(
  () => route.query,
  (q) => {
    form.value = parseSearch(q)
    if (q.prefill !== '1') void run(form.value)
  },
  { immediate: true },
)
onBeforeUnmount(() => retryTimer && clearTimeout(retryTimer))

async function submit() {
  chips.value?.commit()
  const query = toQuery(form.value)
  const same = JSON.stringify(query) === JSON.stringify(toQuery(parseSearch(route.query)))
  if (same && route.query.prefill !== '1') await run(form.value)
  else await router.push({ path: '/search', query })
}

/** 상태 때문에 빠진 마감 공고도 보이게: 상태만 '전체'로 바꿔 다시 검색(URL에도 남는다). */
function showClosed() {
  form.value = { ...form.value, status: 'all' }
  void submit()
}

function reset() {
  form.value = defaultState()
}

function useRecent(q: Record<string, unknown>) {
  form.value = fromRunQuery(q)
  void submit()
}

function recentLabel(q: Record<string, unknown>): string {
  const words = Array.isArray(q.keywords) ? q.keywords.map(String) : []
  if (typeof q.title === 'string' && q.title) words.push(copy.search.titleChip(q.title))
  const kws = words.length ? words.join(', ') : copy.search.noKeywords
  const days = Number(q.days)
  return days ? `${kws} · ${copy.search.recentDays(days)}` : kws
}

async function more() {
  if (!result.value) return
  loadingMore.value = true
  try {
    const page = await libraryApi.run(result.value.run_id, items.value.length)
    items.value = [...items.value, ...page.items]
  } catch {
    failed.value = true
  } finally {
    loadingMore.value = false
  }
}

const sortOptions: Array<{ value: SearchState['sort']; label: string }> = [
  { value: 'notice_desc', label: copy.search.sortNotice },
  { value: 'deadline_asc', label: copy.search.sortDeadline },
  { value: 'budget_desc', label: copy.search.sortBudget },
]
function onSort(v: SearchState['sort']) {
  form.value.sort = v
  void submit()
}

const hasMore = computed(() => !!result.value && items.value.length < result.value.total)
const setView = (v: 'cards' | 'table') => {
  form.value.view = v
  void router.replace({ query: { ...route.query, view: v === 'cards' ? undefined : v } })
}
const view = computed({ get: () => form.value.view, set: setView })
const toggleBookmark = useBookmarkToggle(items)
</script>

<template>
  <div class="flex flex-col gap-4">
    <div v-if="recent.data.value?.items.length" class="flex flex-wrap items-center gap-2">
      <span class="text-xs font-semibold text-text-3">{{ copy.search.recent }}</span>
      <button
        v-for="r in recent.data.value.items"
        :key="r.id"
        type="button"
        class="h-8 rounded-control border border-border bg-surface px-3 text-sm text-text-2 hover:border-primary hover:text-primary"
        @click="useRecent(r.query)"
      >
        {{ recentLabel(r.query) }}
      </button>
    </div>

    <!-- 조건 카드 (2026-11-18, 시안 D): 1줄 키워드·일치·공고명·검색, 2줄 구분·기간·상태·예산·기관·초기화 -->
    <form
      id="search-form"
      :aria-label="copy.search.formLabel"
      class="flex flex-col gap-3 rounded-card border border-border bg-surface px-3.5 py-3"
      @submit.prevent="submit"
    >
      <div class="flex flex-wrap items-center gap-3">
        <div class="min-w-0 flex-[1_1_420px]">
          <ChipInput
            ref="chips"
            v-model="form.keywords"
            :label="copy.search.keywords"
            :hint="copy.search.keywordsHint"
            :placeholder="copy.search.keywordsPlaceholder"
            hide-label
            :max="10"
          />
        </div>
        <UiSegmented
          v-model="form.match"
          :label="copy.search.match"
          hide-label
          :options="[
            { value: 'all', label: copy.search.matchAll },
            { value: 'any', label: copy.search.matchAny },
          ]"
        />
        <div class="w-full sm:w-72">
          <UiInput
            v-model="form.title"
            name="title"
            :label="copy.search.title"
            :placeholder="copy.search.titlePlaceholder"
            hide-label
            :max-length="200"
          />
        </div>
        <UiButton type="submit" :loading="loading">{{ copy.search.submit }}</UiButton>
      </div>
      <div class="flex flex-wrap items-center gap-x-5 gap-y-2.5 border-t border-border pt-3">
        <div class="flex items-center gap-2">
          <span class="text-xs font-semibold text-text-3" aria-hidden="true">{{ copy.search.source }}</span>
          <UiSegmented
            v-model="form.source"
            :label="copy.search.source"
            hide-label
            :options="[
              { value: 'all', label: copy.search.sourceAll },
              { value: 'regular', label: copy.bid.regular },
              { value: 'prespec', label: copy.bid.prespec },
            ]"
          />
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-xs font-semibold text-text-3" aria-hidden="true">{{ copy.search.period }}</span>
          <UiSegmented v-model="form.period" :label="copy.search.period" hide-label :options="periodOptions" />
          <template v-if="form.period === 'custom'">
            <div class="w-40"><UiInput v-model="form.from" type="date" :label="copy.search.from" hide-label /></div>
            <span class="text-text-3" aria-hidden="true">~</span>
            <div class="w-40"><UiInput v-model="form.to" type="date" :label="copy.search.to" hide-label /></div>
          </template>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-xs font-semibold text-text-3" aria-hidden="true">{{ copy.search.status }}</span>
          <UiSegmented
            v-model="form.status"
            :label="copy.search.status"
            hide-label
            :options="[
              { value: 'open', label: copy.search.statusOpen },
              { value: 'closed', label: copy.search.statusClosed },
              { value: 'failed', label: copy.search.statusFailed },
              { value: 'all', label: copy.search.statusAll },
            ]"
          />
        </div>
        <div class="flex items-center gap-2">
          <span class="text-xs font-semibold text-text-3" aria-hidden="true">{{ copy.search.budget }}</span>
          <div class="w-28">
            <UiInput v-model="form.budgetMin" type="number" :label="copy.search.budgetMin" hide-label />
          </div>
          <span class="text-text-3" aria-hidden="true">~</span>
          <div class="w-28">
            <UiInput
              v-model="form.budgetMax"
              type="number"
              :label="copy.search.budgetMax"
              :placeholder="copy.search.budgetMaxPlaceholder"
              hide-label
            />
          </div>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-xs font-semibold text-text-3" aria-hidden="true">{{ copy.search.org }}</span>
          <div class="w-44">
            <UiInput
              v-model="form.org"
              :label="copy.search.org"
              :placeholder="copy.search.orgPlaceholder"
              hide-label
              :max-length="100"
            />
          </div>
        </div>
        <UiButton variant="ghost" class="lg:ml-auto" @click="reset">{{ copy.search.reset }}</UiButton>
      </div>
      <p class="text-xs text-text-3">{{ copy.search.budgetMinHint }}</p>
    </form>

    <UiSkeleton v-if="loading" :lines="4" />
    <div v-else-if="failed" class="flex flex-col items-start gap-2 rounded-card border border-border bg-surface p-4" role="alert">
      <p class="text-base text-danger-fg">{{ copy.search.error }}</p>
      <UiButton variant="secondary" size="sm" @click="run(form)">{{ copy.common.retry }}</UiButton>
    </div>
    <template v-else-if="result">
      <div class="flex flex-wrap items-center gap-3" aria-live="polite">
        <span class="text-base font-semibold tabular">{{ copy.search.total(result.total) }}</span>
        <DataAsOfBadge :as-of="result.data_as_of" :incomplete="result.incomplete" />
        <UiBadge v-if="result.collecting" tone="warning">{{ copy.data.collecting }}</UiBadge>
        <div class="ml-auto flex flex-wrap items-center gap-2">
          <ExportButton :bid-ids="items.map((b) => b.bid_id)" />
          <UiSegmented
            :model-value="form.sort"
            :label="copy.search.sort"
            hide-label
            :options="sortOptions"
            @update:model-value="onSort"
          />
          <UiSegmented
            v-model="view"
            :label="copy.search.view"
            hide-label
            :options="[
              { value: 'cards', label: copy.search.viewCards },
              { value: 'table', label: copy.search.viewTable },
            ]"
          />
        </div>
      </div>
      <p v-if="result.truncated" class="text-sm text-warning-fg">{{ copy.search.truncated }}</p>
      <p v-if="items.length && result.hidden_closed" class="flex flex-wrap items-center gap-2 text-sm text-text-2">
        {{ copy.search.hiddenClosed(result.hidden_closed) }}
        <UiButton variant="secondary" size="sm" data-show-closed @click="showClosed">{{ copy.search.showClosed }}</UiButton>
      </p>
      <EmptyState v-if="!items.length && result.hidden_closed" :title="copy.search.emptyOpenOnly(result.hidden_closed)">
        <template #action>
          <UiButton variant="secondary" data-show-closed @click="showClosed">{{ copy.search.emptyShowClosed }}</UiButton>
        </template>
      </EmptyState>
      <EmptyState v-else-if="!items.length" :title="copy.search.empty" />
      <BidList v-else :bids="items" :view="form.view" @toggle-bookmark="toggleBookmark" />
      <div v-if="hasMore" class="flex justify-center">
        <UiButton variant="secondary" :loading="loadingMore" @click="more">{{ copy.common.more }}</UiButton>
      </div>
    </template>
  </div>
</template>

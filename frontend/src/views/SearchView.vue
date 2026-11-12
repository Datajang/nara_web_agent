<script setup lang="ts">
// 공고 검색 (SPEC §7.3). 조건은 URL과 동기화하고, 결과는 DB-first 검색(§6.3)의 스냅샷을 쓴다.
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { ChevronDown } from 'lucide-vue-next'
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
import UiSegmented from '@/components/ui/UiSegmented.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
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
const open = ref(true)
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

function reset() {
  form.value = defaultState()
}

function useRecent(q: Record<string, unknown>) {
  form.value = fromRunQuery(q)
  void submit()
}

function recentLabel(q: Record<string, unknown>): string {
  const kws = Array.isArray(q.keywords) && q.keywords.length ? q.keywords.join(', ') : copy.search.noKeywords
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
    <section class="rounded-card border border-border bg-surface" :aria-label="copy.search.formLabel">
      <button
        type="button"
        class="flex h-12 w-full items-center justify-between px-4 text-base font-semibold"
        :aria-expanded="open"
        aria-controls="search-form"
        @click="open = !open"
      >
        {{ copy.search.formLabel }}
        <ChevronDown class="size-4 transition-transform" :class="open ? 'rotate-180' : ''" aria-hidden="true" />
      </button>
      <form
        v-show="open"
        id="search-form"
        class="grid gap-4 border-t border-border p-4 md:grid-cols-2"
        @submit.prevent="submit"
      >
        <div class="md:col-span-2">
          <ChipInput
            ref="chips"
            v-model="form.keywords"
            :label="copy.search.keywords"
            :hint="copy.search.keywordsHint"
            :max="10"
          />
        </div>
        <UiSegmented
          v-model="form.match"
          :label="copy.search.match"
          :options="[
            { value: 'all', label: copy.search.matchAll },
            { value: 'any', label: copy.search.matchAny },
          ]"
        />
        <UiSegmented
          v-model="form.status"
          :label="copy.search.status"
          :options="[
            { value: 'open', label: copy.search.statusOpen },
            { value: 'all', label: copy.search.statusAll },
          ]"
        />
        <div class="md:col-span-2">
          <UiSegmented v-model="form.period" :label="copy.search.period" :options="periodOptions" />
          <div v-if="form.period === 'custom'" class="mt-3 grid grid-cols-2 gap-3 sm:max-w-md">
            <UiInput v-model="form.from" type="date" :label="copy.search.from" />
            <UiInput v-model="form.to" type="date" :label="copy.search.to" />
          </div>
        </div>
        <UiSelect
          v-model="form.source"
          :label="copy.search.source"
          :options="[
            { value: 'all', label: copy.search.sourceAll },
            { value: 'regular', label: copy.bid.regular },
            { value: 'prespec', label: copy.bid.prespec },
          ]"
        />
        <UiSelect
          v-model="form.sort"
          :label="copy.search.sort"
          :options="[
            { value: 'notice_desc', label: copy.search.sortNotice },
            { value: 'deadline_asc', label: copy.search.sortDeadline },
            { value: 'budget_desc', label: copy.search.sortBudget },
          ]"
        />
        <div class="grid grid-cols-2 gap-3">
          <UiInput v-model="form.budgetMin" type="number" :label="copy.search.budgetMin" />
          <UiInput v-model="form.budgetMax" type="number" :label="copy.search.budgetMax" />
        </div>
        <UiInput v-model="form.org" :label="copy.search.org" :max-length="100" />
        <div class="flex gap-2 md:col-span-2">
          <UiButton type="submit" :loading="loading">{{ copy.search.submit }}</UiButton>
          <UiButton variant="ghost" @click="reset">{{ copy.search.reset }}</UiButton>
        </div>
      </form>
      <div v-if="recent.data.value?.items.length" class="flex flex-wrap items-center gap-2 border-t border-border px-4 py-3">
        <span class="text-sm text-text-3">{{ copy.search.recent }}</span>
        <button
          v-for="r in recent.data.value.items"
          :key="r.id"
          type="button"
          class="h-8 rounded-control border border-border-input px-3 text-sm text-text-2 hover:bg-surface-2"
          @click="useRecent(r.query)"
        >
          {{ recentLabel(r.query) }}
        </button>
      </div>
    </section>

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
        <div class="ml-auto">
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
      <EmptyState v-if="!items.length" :title="copy.search.empty" />
      <BidList v-else :bids="items" :view="form.view" @toggle-bookmark="toggleBookmark" />
      <div v-if="hasMore" class="flex justify-center">
        <UiButton variant="secondary" :loading="loadingMore" @click="more">{{ copy.common.more }}</UiButton>
      </div>
    </template>
  </div>
</template>

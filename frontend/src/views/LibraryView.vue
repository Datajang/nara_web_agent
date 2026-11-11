<script setup lang="ts">
// 내 기록 (SPEC §7.7): 검색 기록(스냅샷 다시 보기·다시 검색), 분석 기록, 북마크(메모·검색·정렬).
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { bidsApi } from '@/api/bids'
import { libraryApi } from '@/api/library'
import type { BidCard, Bookmark, SearchRun, SearchRunDetail } from '@/api/types'
import BidCardView from '@/components/bid/BidCard.vue'
import BidList from '@/components/bid/BidList.vue'
import ScoreBadge from '@/components/bid/ScoreBadge.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import UiTabs from '@/components/ui/UiTabs.vue'
import UiTextarea from '@/components/ui/UiTextarea.vue'
import { fromRunQuery, toQuery } from '@/composables/useUrlState'
import { copy } from '@/copy'
import { useUiStore } from '@/stores/ui'
import { generalMessage } from '@/utils/authErrors'
import { formatDateTime } from '@/utils/format'

type Tab = 'runs' | 'analyses' | 'bookmarks'
const TABS: Array<{ value: Tab; label: string }> = [
  { value: 'runs', label: copy.library.tabRuns },
  { value: 'analyses', label: copy.library.tabAnalyses },
  { value: 'bookmarks', label: copy.library.tabBookmarks },
]

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const queryClient = useQueryClient()
const tab = computed<Tab>({
  get: () => TABS.find((t) => t.value === route.query.tab)?.value ?? 'runs',
  set: (v) => void router.replace({ query: { tab: v } }),
})

const runs = useQuery({
  queryKey: ['search-runs', 'all'],
  queryFn: () => libraryApi.runs(undefined, 100),
  enabled: computed(() => tab.value === 'runs'),
})
const analyses = useQuery({
  queryKey: ['analyses'],
  queryFn: () => libraryApi.analyses(100),
  enabled: computed(() => tab.value === 'analyses'),
})
const bookmarks = useQuery({
  queryKey: ['bookmarks'],
  queryFn: () => libraryApi.bookmarks(),
  enabled: computed(() => tab.value === 'bookmarks'),
})

async function act(
  fn: () => Promise<unknown>,
  key: string[],
  message: string = copy.library.removed,
) {
  try {
    await fn()
    ui.toast(message, 'success')
    await queryClient.invalidateQueries({ queryKey: key })
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  }
}

// ---------- 검색 기록 ----------
const snapshot = ref<SearchRunDetail | null>(null)
const snapshotItems = ref<BidCard[]>([])
async function openRun(r: SearchRun) {
  try {
    snapshot.value = await libraryApi.run(r.id, 0, 100)
    snapshotItems.value = snapshot.value.items
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  }
}
function rerun(r: SearchRun) {
  if (r.kind === 'recommend') void router.push('/recommend')
  else void router.push({ path: '/search', query: toQuery(fromRunQuery(r.query)) })
}
function runSummary(r: SearchRun): string {
  const kws = Array.isArray(r.query.keywords) && r.query.keywords.length
    ? (r.query.keywords as string[]).join(', ')
    : copy.search.noKeywords
  const days = Number(r.query.days)
  return days ? `${kws} · ${copy.search.recentDays(days)}` : kws
}
watch(tab, () => (snapshot.value = null))

// ---------- 북마크 ----------
const filter = ref('')
const sort = ref<'recent' | 'deadline'>('recent')
const notes = ref<Record<string, string>>({})
watch(
  () => bookmarks.data.value?.items,
  (items) => {
    for (const b of items ?? []) notes.value[b.bid.bid_id] ??= b.note
  },
  { immediate: true },
)
const shownBookmarks = computed(() => {
  const q = filter.value.trim().toLowerCase()
  const list = (bookmarks.data.value?.items ?? []).filter(
    (b) => !q || b.bid.title.toLowerCase().includes(q),
  )
  if (sort.value === 'deadline') {
    const t = (b: Bookmark) => (b.bid.deadline_at ? Date.parse(b.bid.deadline_at) : Infinity)
    return [...list].sort((a, b) => t(a) - t(b))
  }
  return list
})
function saveNote(b: Bookmark) {
  void act(
    () => bidsApi.bookmark(b.bid.bid_id, notes.value[b.bid.bid_id] ?? '', b.analysis_id),
    ['bookmarks'],
    copy.library.noteSaved,
  )
}
function unbookmark(b: BidCard) {
  void act(() => bidsApi.unbookmark(b.bid_id), ['bookmarks'], copy.bid.unbookmarked)
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <UiTabs v-model="tab" :items="TABS" :label="copy.library.tabsLabel" />

    <!-- 검색 기록 -->
    <template v-if="tab === 'runs'">
      <template v-if="snapshot">
        <div class="flex items-center gap-2">
          <UiButton variant="ghost" size="sm" @click="snapshot = null">{{ copy.library.back }}</UiButton>
          <UiButton variant="secondary" size="sm" @click="rerun(snapshot)">{{ copy.library.rerun }}</UiButton>
          <span class="text-base text-text-2">{{ copy.library.snapshot }} · {{ formatDateTime(snapshot.created_at) }}</span>
        </div>
        <BidList :bids="snapshotItems" :show-score="snapshot.kind === 'recommend'" />
      </template>
      <UiSkeleton v-else-if="runs.isPending.value" />
      <EmptyState v-else-if="!runs.data.value?.items.length" :title="copy.library.emptyRuns" />
      <ul v-else class="divide-y divide-border rounded-card border border-border bg-surface">
        <li v-for="r in runs.data.value.items" :key="r.id" class="flex flex-wrap items-center gap-3 px-4 py-3">
          <UiBadge :tone="r.kind === 'recommend' ? 'primary' : 'neutral'">
            {{ r.kind === 'recommend' ? copy.library.kindRecommend : copy.library.kindSearch }}
          </UiBadge>
          <span class="min-w-0 flex-1 truncate text-base">{{ runSummary(r) }}</span>
          <span class="text-sm tabular text-text-3">{{ copy.library.results(r.result_count) }}</span>
          <span class="text-sm tabular text-text-3">{{ formatDateTime(r.created_at) }}</span>
          <div class="flex gap-1">
            <UiButton size="sm" variant="secondary" @click="openRun(r)">{{ copy.library.open }}</UiButton>
            <UiButton size="sm" variant="ghost" @click="rerun(r)">{{ copy.library.rerun }}</UiButton>
            <UiButton size="sm" variant="ghost" @click="act(() => libraryApi.deleteRun(r.id), ['search-runs'])">
              {{ copy.library.remove }}
            </UiButton>
          </div>
        </li>
      </ul>
    </template>

    <!-- 분석 기록 -->
    <template v-else-if="tab === 'analyses'">
      <UiSkeleton v-if="analyses.isPending.value" />
      <EmptyState v-else-if="!analyses.data.value?.items.length" :title="copy.library.emptyAnalyses" />
      <ul v-else class="divide-y divide-border rounded-card border border-border bg-surface">
        <li v-for="a in analyses.data.value.items" :key="a.analysis_id" class="flex flex-wrap items-center gap-3 px-4 py-3">
          <RouterLink
            :to="`/bids/${a.bid.bid_id}?analysis=${a.analysis_id}`"
            class="min-w-0 flex-1 truncate text-base font-medium text-text hover:underline"
          >{{ a.bid.title }}</RouterLink>
          <ScoreBadge :score="a.fit_score" />
          <span class="text-sm text-text-2">{{ a.profile_name || copy.library.profileDeleted }}</span>
          <span class="text-sm tabular text-text-3">{{ formatDateTime(a.created_at) }}</span>
          <UiButton size="sm" variant="ghost" @click="act(() => libraryApi.deleteAnalysis(a.analysis_id), ['analyses'])">
            {{ copy.library.remove }}
          </UiButton>
        </li>
      </ul>
    </template>

    <!-- 북마크 -->
    <template v-else>
      <div class="flex flex-wrap items-end gap-3">
        <input
          v-model="filter"
          type="search"
          :aria-label="copy.library.filterTitle"
          :placeholder="copy.library.filterTitle"
          class="h-10 w-64 rounded-control border border-border-input bg-surface px-3 text-base"
        />
        <div class="w-44">
          <UiSelect
            v-model="sort"
            :label="copy.library.sort"
            hide-label
            :options="[
              { value: 'recent', label: copy.library.sortRecent },
              { value: 'deadline', label: copy.library.sortDeadline },
            ]"
          />
        </div>
      </div>
      <UiSkeleton v-if="bookmarks.isPending.value" />
      <EmptyState v-else-if="!bookmarks.data.value?.items.length" :title="copy.library.emptyBookmarks" />
      <ul v-else class="grid gap-3">
        <li v-for="b in shownBookmarks" :key="b.bid.bid_id" class="flex flex-col gap-2">
          <BidCardView :bid="b.bid" @toggle-bookmark="unbookmark" />
          <div class="flex flex-col gap-2 rounded-card border border-border bg-surface p-3">
            <UiTextarea v-model="notes[b.bid.bid_id]" :label="copy.library.note" :rows="2" :max-length="1000" />
            <div class="flex flex-wrap gap-2">
              <UiButton size="sm" variant="secondary" @click="saveNote(b)">{{ copy.library.noteSave }}</UiButton>
              <RouterLink
                v-if="b.analysis_id"
                :to="`/bids/${b.bid.bid_id}?analysis=${b.analysis_id}`"
                class="inline-flex h-8 items-center px-2 text-sm text-primary-hover hover:underline"
              >{{ copy.library.openAnalysis }}</RouterLink>
            </div>
          </div>
        </li>
      </ul>
    </template>
  </div>
</template>

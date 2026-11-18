<script setup lang="ts">
// 관심 공고 홈 (SPEC §13 P6). 팀·개인 키워드에 맞는 진행 중 공고를 마감 임박 순으로. DB만 읽는다.
// 키워드가 3개 미만이면 키워드 설정으로 보낸다.
// 보기(2026-11-18): 기본은 마감 보드(칸마다 한 번씩 부름), 목록은 예전처럼 20건씩. 보기는 주소(view=list)에 남긴다.
// 안에서 좁히기(2026-11-16): 공고명·공고 종류·맞은 키워드. 2026-11-18부터 한 줄 조건 막대(UiFilterBar). 조건은 주소(q·source·kw)에 남겨
// 상세에서 돌아와도 그대로 보인다.
import { Pencil } from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter, type LocationQuery } from 'vue-router'
import { authApi } from '@/api/auth'
import { DUE_WINDOWS, feedApi, type Due, type Feed, type FeedFilter, type FeedItem } from '@/api/teams'
import BidCard from '@/components/bid/BidCard.vue'
import FeedBoard, { type BoardColumn } from '@/components/bid/FeedBoard.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiFilterBar from '@/components/ui/UiFilterBar.vue'
import UiSegmented from '@/components/ui/UiSegmented.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useBookmarkToggle } from '@/composables/useBookmarkToggle'
import { copy } from '@/copy'

type Source = NonNullable<FeedFilter['source']>
type View = 'board' | 'list'
const PAGE = 20
const BOARD_PAGE = 6 // 보드 칸마다 처음 보여 줄 수, 더 보기도 같은 수만큼
const TYPING_MS = 300
const router = useRouter()
const route = useRoute()
const keywords = ref<string[]>([])
const items = ref<FeedItem[]>([])
const total = ref(0)
const loading = ref(true)
const refreshing = ref(false)
const loadingMore = ref(false)
const failed = ref(false)
// 기본은 1억 원 이상만. 켜면 1억 미만도 — 계정에 저장한다 (2026-11-16)
const includeSmall = ref(false)
const savingSmall = ref(false)

const list = (v: LocationQuery[string] | undefined) => (Array.isArray(v) ? v : v ? [v] : []).filter((x): x is string => !!x)
const first = (v: LocationQuery[string] | undefined) => list(v)[0] ?? ''
const q = ref(first(route.query.q).slice(0, 200))
const source = ref<Source>((['regular', 'prespec'] as const).find((x) => x === first(route.query.source)) ?? 'all')
const picked = ref<string[]>(list(route.query.kw))
const view = ref<View>(first(route.query.view) === 'list' ? 'list' : 'board')
const viewOptions: Array<{ value: View; label: string }> = [
  { value: 'board', label: copy.feed.viewBoard },
  { value: 'list', label: copy.feed.viewList },
]
// 보드: 칸별 공고(북마크 토글이 한 목록을 고치도록 평평하게, due로 칸을 나눈다)와 칸 건수
const boardItems = ref<Array<FeedItem & { due: Due }>>([])
const dueTotals = ref<Record<Due, number>>({ today: 0, d3: 0, d7: 0, later: 0 })
const loadingDue = ref<Due | null>(null)
const columns = computed<BoardColumn[]>(() =>
  DUE_WINDOWS.map((d) => ({
    due: d,
    total: dueTotals.value[d],
    items: boardItems.value.filter((b) => b.due === d),
    loading: loadingDue.value === d,
  })),
)
const isEmpty = computed(() => (view.value === 'board' ? total.value === 0 : !items.value.length))
const filtered = computed(() => !!q.value.trim() || source.value !== 'all' || picked.value.length > 0)
const sourceOptions: Array<{ value: Source; label: string }> = [
  { value: 'all', label: copy.feed.sourceAll },
  { value: 'regular', label: copy.bid.regular },
  { value: 'prespec', label: copy.bid.prespec },
]

let seq = 0 // 늦게 온 예전 응답이 새 결과를 덮지 않게
const filter = (): FeedFilter => ({ q: q.value, source: source.value, kw: picked.value })

/** 응답 공통 처리. 키워드 설정으로 보냈으면 false. */
async function applyMeta(f: Feed): Promise<boolean> {
  if (f.needs_keywords) {
    await router.replace('/onboarding')
    return false
  }
  keywords.value = f.keywords
  includeSmall.value = f.min_budget == null
  const known = picked.value.filter((k) => f.keywords.includes(k))
  if (known.length !== picked.value.length) {
    picked.value = known // 내 키워드에서 빠진 값은 서버도 무시한다. 주소만 정리
    syncUrl()
  }
  return true
}

async function load(offset = 0) {
  if (view.value === 'board') return loadBoard()
  const mine = ++seq
  try {
    const f = await feedApi.get(offset, PAGE, filter())
    if (mine !== seq) return
    if (!(await applyMeta(f))) return
    total.value = f.total
    items.value = offset ? [...items.value, ...f.items] : f.items
    failed.value = false
  } catch {
    if (mine === seq) failed.value = true
  }
}

async function loadBoard() {
  const mine = ++seq
  try {
    const got = await Promise.all(DUE_WINDOWS.map((d) => feedApi.get(0, BOARD_PAGE, { ...filter(), due: d })))
    if (mine !== seq) return
    if (!(await applyMeta(got[0]!))) return
    boardItems.value = got.flatMap((f, i) => f.items.map((b) => ({ ...b, due: DUE_WINDOWS[i]! })))
    dueTotals.value = Object.fromEntries(DUE_WINDOWS.map((d, i) => [d, got[i]!.total])) as Record<Due, number>
    total.value = got.reduce((n, f) => n + f.total, 0)
    failed.value = false
  } catch {
    if (mine === seq) failed.value = true
  }
}

async function moreInColumn(d: Due) {
  loadingDue.value = d
  try {
    const shown = boardItems.value.filter((b) => b.due === d).length
    const f = await feedApi.get(shown, BOARD_PAGE, { ...filter(), due: d })
    boardItems.value = [...boardItems.value, ...f.items.map((b) => ({ ...b, due: d }))]
    dueTotals.value = { ...dueTotals.value, [d]: f.total }
  } catch {
    failed.value = true
  } finally {
    loadingDue.value = null
  }
}

function syncUrl() {
  const query: Record<string, string | string[]> = {}
  if (q.value.trim()) query.q = q.value.trim()
  if (source.value !== 'all') query.source = source.value
  if (picked.value.length) query.kw = picked.value.length === 1 ? picked.value[0]! : [...picked.value]
  if (view.value === 'list') query.view = 'list'
  void router.replace({ query })
}

let typing: ReturnType<typeof setTimeout> | undefined
async function apply() {
  clearTimeout(typing)
  syncUrl()
  refreshing.value = true
  await load()
  refreshing.value = false
}

function onQuery(v: string) {
  q.value = v
  clearTimeout(typing)
  typing = setTimeout(apply, TYPING_MS)
}
function onSource(v: Source) {
  source.value = v
  void apply()
}
function onView(v: View) {
  view.value = v
  void apply()
}
function toggleKeyword(k: string) {
  picked.value = picked.value.includes(k) ? picked.value.filter((x) => x !== k) : [...picked.value, k]
  void apply()
}
function clearFilters() {
  q.value = ''
  source.value = 'all'
  picked.value = []
  void apply()
}

onMounted(async () => {
  await load()
  loading.value = false
})
onBeforeUnmount(() => clearTimeout(typing))

async function setIncludeSmall(v: boolean) {
  savingSmall.value = true
  try {
    await authApi.updateMe({ feed_include_small: v })
    await load()
  } catch {
    failed.value = true
  } finally {
    savingSmall.value = false
  }
}

async function more() {
  loadingMore.value = true
  await load(items.value.length)
  loadingMore.value = false
}

const toggleBookmark = useBookmarkToggle(items)
const toggleBoardBookmark = useBookmarkToggle(boardItems)
</script>

<template>
  <div class="flex flex-col gap-4">
    <UiFilterBar :label="copy.feed.filters">
      <div class="w-full sm:w-72">
        <UiInput
          :model-value="q"
          type="search"
          name="feed-q"
          :label="copy.feed.search"
          hide-label
          :placeholder="copy.feed.searchPlaceholder"
          :max-length="200"
          @update:model-value="onQuery"
        />
      </div>
      <UiSegmented
        :model-value="source"
        :label="copy.feed.source"
        hide-label
        :options="sourceOptions"
        @update:model-value="onSource"
      />
      <template v-if="keywords.length">
        <span class="hidden h-6 w-px bg-border sm:block" aria-hidden="true" />
        <div
          role="group"
          :aria-label="copy.feed.keywords"
          aria-describedby="feed-kw-hint"
          class="flex flex-wrap items-center gap-1.5"
        >
          <span class="text-sm text-text-3" aria-hidden="true">{{ copy.feed.keywords }}</span>
          <span id="feed-kw-hint" class="sr-only">{{ copy.feed.keywordsHint }}</span>
          <button
            v-for="k in keywords"
            :key="k"
            type="button"
            data-kw
            :aria-pressed="picked.includes(k) ? 'true' : 'false'"
            class="inline-flex h-8 items-center rounded-tag border px-2.5 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-primary"
            :class="
              picked.includes(k)
                ? 'border-primary bg-primary text-white hover:bg-primary-hover'
                : picked.length
                  ? 'border-border bg-surface text-text-3 hover:border-primary/40 hover:text-text-2'
                  : 'border-primary/25 bg-primary-soft text-primary-hover hover:border-primary/50'
            "
            @click="toggleKeyword(k)"
          >
            {{ k }}
          </button>
          <RouterLink
            to="/onboarding"
            class="inline-flex h-8 items-center gap-1 rounded-control px-2 text-sm text-text-2 hover:bg-surface-2 hover:text-text"
          >
            <Pencil class="size-3.5" aria-hidden="true" />{{ copy.feed.editKeywords }}
          </RouterLink>
        </div>
      </template>
      <template #end>
        <label class="inline-flex h-8 items-center gap-2 text-sm text-text-2">
          <input
            name="feed-small"
            type="checkbox"
            class="size-4 accent-primary"
            :checked="includeSmall"
            :disabled="savingSmall"
            @change="setIncludeSmall(($event.target as HTMLInputElement).checked)"
          />
          {{ copy.feed.includeSmall }}
        </label>
      </template>
    </UiFilterBar>

    <div v-if="loading" class="grid gap-3">
      <UiSkeleton v-for="i in 3" :key="i" class="h-28" />
    </div>
    <p v-else-if="failed" class="text-danger-fg">{{ copy.feed.failed }}</p>
    <EmptyState v-else-if="isEmpty && filtered" :title="copy.feed.emptyFiltered">
      <template #action>
        <UiButton variant="secondary" @click="clearFilters">{{ copy.feed.clearFilters }}</UiButton>
      </template>
    </EmptyState>
    <EmptyState v-else-if="isEmpty" :title="copy.feed.empty" />
    <template v-else>
      <div class="flex flex-wrap items-center gap-3">
        <p class="text-sm text-text-2" aria-live="polite">
          <strong class="text-md font-semibold text-text">{{ copy.feed.total(total) }}</strong>
          · {{ copy.feed.order }}<template v-if="!includeSmall"> · {{ copy.feed.minBudgetNote }}</template>
        </p>
        <button
          v-if="filtered"
          type="button"
          class="text-sm font-medium text-text-2 underline hover:text-text"
          @click="clearFilters"
        >
          {{ copy.feed.clearFilters }}
        </button>
        <div class="ml-auto">
          <UiSegmented
            :model-value="view"
            :label="copy.feed.view"
            hide-label
            :options="viewOptions"
            @update:model-value="onView"
          />
        </div>
      </div>
      <FeedBoard
        v-if="view === 'board'"
        :columns="columns"
        class="transition-opacity"
        :class="refreshing ? 'opacity-60' : ''"
        :aria-busy="refreshing ? 'true' : 'false'"
        @more="moreInColumn"
        @toggle-bookmark="toggleBoardBookmark"
      />
      <ul
        v-else
        class="divide-y divide-border overflow-hidden rounded-card border border-border bg-surface transition-opacity"
        :class="refreshing ? 'opacity-60' : ''"
        :aria-busy="refreshing ? 'true' : 'false'"
      >
        <li v-for="b in items" :key="b.bid_id">
          <BidCard :bid="b" @toggle-bookmark="toggleBookmark">
            <p class="flex flex-wrap items-center gap-1.5 text-xs text-text-3">
              <span>{{ copy.feed.matched }}</span>
              <span
                v-for="k in b.matched_keywords"
                :key="k"
                data-matched
                class="border-b border-primary/40 text-text-2"
              >{{ k }}</span>
            </p>
          </BidCard>
        </li>
      </ul>
      <UiButton v-if="view === 'list' && items.length < total" variant="secondary" :loading="loadingMore" @click="more">
        {{ copy.feed.more }}
      </UiButton>
    </template>
  </div>
</template>

<script setup lang="ts">
// 관심 공고 홈 (SPEC §13 P6). 팀·개인 키워드에 맞는 진행 중 공고를 마감 임박 순으로. DB만 읽는다.
// 키워드가 3개 미만이면 키워드 설정으로 보낸다.
// 안에서 좁히기(2026-11-16): 공고명·공고 종류·맞은 키워드. 조건은 주소(q·source·kw)에 남겨
// 상세에서 돌아와도 그대로 보인다.
import { Pencil } from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter, type LocationQuery } from 'vue-router'
import { authApi } from '@/api/auth'
import { feedApi, type FeedFilter, type FeedItem } from '@/api/teams'
import BidCard from '@/components/bid/BidCard.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiSegmented from '@/components/ui/UiSegmented.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useBookmarkToggle } from '@/composables/useBookmarkToggle'
import { copy } from '@/copy'

type Source = NonNullable<FeedFilter['source']>
const PAGE = 20
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
const filtered = computed(() => !!q.value.trim() || source.value !== 'all' || picked.value.length > 0)
const sourceOptions: Array<{ value: Source; label: string }> = [
  { value: 'all', label: copy.feed.sourceAll },
  { value: 'regular', label: copy.bid.regular },
  { value: 'prespec', label: copy.bid.prespec },
]

let seq = 0 // 늦게 온 예전 응답이 새 결과를 덮지 않게
async function load(offset = 0) {
  const mine = ++seq
  try {
    const f = await feedApi.get(offset, PAGE, { q: q.value, source: source.value, kw: picked.value })
    if (mine !== seq) return
    if (f.needs_keywords) {
      await router.replace('/onboarding')
      return
    }
    keywords.value = f.keywords
    includeSmall.value = f.min_budget == null
    total.value = f.total
    items.value = offset ? [...items.value, ...f.items] : f.items
    failed.value = false
    const known = picked.value.filter((k) => f.keywords.includes(k))
    if (known.length !== picked.value.length) {
      picked.value = known // 내 키워드에서 빠진 값은 서버도 무시한다. 주소만 정리
      syncUrl()
    }
  } catch {
    if (mine === seq) failed.value = true
  }
}

function syncUrl() {
  const query: Record<string, string | string[]> = {}
  if (q.value.trim()) query.q = q.value.trim()
  if (source.value !== 'all') query.source = source.value
  if (picked.value.length) query.kw = picked.value.length === 1 ? picked.value[0]! : [...picked.value]
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
</script>

<template>
  <div class="flex flex-col gap-5">
    <section class="flex flex-col gap-4">
      <p class="text-md text-text-2">{{ copy.feed.lead }}</p>
      <div v-if="keywords.length" class="flex flex-col gap-1.5">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-sm text-text-3">{{ copy.feed.keywords }}</span>
          <button
            v-for="k in keywords"
            :key="k"
            type="button"
            data-kw
            :aria-pressed="picked.includes(k) ? 'true' : 'false'"
            class="inline-flex h-7 items-center rounded-tag border px-2 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-primary"
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
            class="inline-flex h-7 items-center gap-1 rounded-control px-2 text-sm text-text-2 hover:bg-surface-2 hover:text-text"
          >
            <Pencil class="size-3.5" aria-hidden="true" />{{ copy.feed.editKeywords }}
          </RouterLink>
        </div>
        <p class="text-xs text-text-3">{{ copy.feed.pickKeywords }}</p>
      </div>
      <div class="flex flex-col gap-3 md:flex-row md:items-start md:gap-6">
        <div class="md:w-80">
          <UiInput
            :model-value="q"
            type="search"
            name="feed-q"
            :label="copy.feed.search"
            :hint="copy.feed.searchHint"
            :max-length="200"
            @update:model-value="onQuery"
          />
        </div>
        <UiSegmented
          :model-value="source"
          :label="copy.feed.source"
          :options="sourceOptions"
          @update:model-value="onSource"
        />
      </div>
      <label class="inline-flex items-center gap-2 text-sm text-text-2">
        <input
          name="feed-small"
          type="checkbox"
          class="size-4"
          :checked="includeSmall"
          :disabled="savingSmall"
          @change="setIncludeSmall(($event.target as HTMLInputElement).checked)"
        />
        {{ copy.feed.includeSmall }}
        <span v-if="!includeSmall" class="text-text-3">{{ copy.feed.minBudgetNote }}</span>
      </label>
    </section>

    <div v-if="loading" class="grid gap-3">
      <UiSkeleton v-for="i in 3" :key="i" class="h-28" />
    </div>
    <p v-else-if="failed" class="text-danger-fg">{{ copy.feed.failed }}</p>
    <EmptyState v-else-if="!items.length && filtered" :title="copy.feed.emptyFiltered">
      <template #action>
        <UiButton variant="secondary" @click="clearFilters">{{ copy.feed.clearFilters }}</UiButton>
      </template>
    </EmptyState>
    <EmptyState v-else-if="!items.length" :title="copy.feed.empty" />
    <template v-else>
      <div class="flex items-center gap-3">
        <p class="text-sm text-text-3" aria-live="polite">{{ copy.feed.total(total) }}</p>
        <button
          v-if="filtered"
          type="button"
          class="text-sm font-medium text-text-2 underline hover:text-text"
          @click="clearFilters"
        >
          {{ copy.feed.clearFilters }}
        </button>
      </div>
      <ul
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
      <UiButton v-if="items.length < total" variant="secondary" :loading="loadingMore" @click="more">
        {{ copy.feed.more }}
      </UiButton>
    </template>
  </div>
</template>

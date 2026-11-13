<script setup lang="ts">
// 공고 상세·분석 (SPEC §7.5). 헤더 → 첨부 → 요약 → 분석 패널 → 분석 결과 → 보조 기능.
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { Bookmark, BookmarkCheck, Copy, ExternalLink } from 'lucide-vue-next'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { bidsApi } from '@/api/bids'
import { ApiError } from '@/api/client'
import { libraryApi } from '@/api/library'
import { profilesApi } from '@/api/profiles'
import type { AnalysisResult, BidDetail, FileText, StreamEvent } from '@/api/types'
import AnalysisResultView from '@/components/bid/AnalysisResultView.vue'
import DeadlineStamp from '@/components/bid/DeadlineStamp.vue'
import FeedbackButtons from '@/components/bid/FeedbackButtons.vue'
import FileList from '@/components/bid/FileList.vue'
import MoneyText from '@/components/bid/MoneyText.vue'
import ProgressSteps from '@/components/bid/ProgressSteps.vue'
import OfficialFacts from '@/components/bid/OfficialFacts.vue'
import SummaryFacts from '@/components/bid/SummaryFacts.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDrawer from '@/components/ui/UiDrawer.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useSse } from '@/composables/useSse'
import { copy } from '@/copy'
import { useUiStore } from '@/stores/ui'
import { generalMessage } from '@/utils/authErrors'
import { saveBlob } from '@/utils/saveBlob'

const IN_PROGRESS_RETRY_MS = 5000
const STAGES = ['files', 'extract', 'summarize', 'analyze'] as const

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const queryClient = useQueryClient()
const bidId = computed(() => String(route.params.bidId))

const detail = useQuery({
  queryKey: computed(() => ['bid', bidId.value]),
  queryFn: () => bidsApi.detail(bidId.value),
})
const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => profilesApi.list() })
const bid = computed<BidDetail | undefined>(() => detail.data.value)
const notFound = computed(
  () => detail.error.value instanceof ApiError && detail.error.value.status === 404,
)

// ---------- 공고번호로 열기 / 키워드는 공고 검색으로 ----------
// 공고번호: 새 나라장터 R26BK01667536 꼴, 옛 20240512345(-00) 꼴. 나머지는 키워드로 본다.
const BID_NO = /^([a-z]\d{2}[a-z]{2}\d{8}|\d{11})(-\d{1,3})?$/i
const bidNo = ref('')
const lookupError = ref('')
async function lookup() {
  lookupError.value = ''
  const no = bidNo.value.trim()
  if (!no) return
  if (!BID_NO.test(no)) {
    bidNo.value = ''
    await router.push({ path: '/search', query: { q: no } })
    return
  }
  try {
    const { bid_id } = await bidsApi.lookup(no)
    bidNo.value = ''
    await router.push(`/bids/${bid_id}`)
  } catch (e) {
    lookupError.value =
      e instanceof ApiError && e.status === 404 ? copy.detail.lookupNotFound : generalMessage(e)
  }
}

// ---------- 첨부 미리보기 ----------
const preview = ref<FileText | null>(null)
const previewOpen = ref(false)
async function openPreview(f: { file_id: number }) {
  try {
    preview.value = await bidsApi.fileText(bidId.value, f.file_id)
    previewOpen.value = true
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  }
}

// ---------- 첨부 원본 내려받기 ----------
const downloading = ref<number | null>(null)
async function download(f: { file_id: number; name: string }) {
  downloading.value = f.file_id
  try {
    saveBlob(await bidsApi.download(bidId.value, f.file_id), f.name)
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  } finally {
    downloading.value = null
  }
}

// ---------- 분석 ----------
const profileId = ref<number | null>(null)
watch(
  () => profiles.data.value?.items,
  (items) => {
    if (items?.length && !items.some((p) => p.id === profileId.value)) {
      profileId.value = (items.find((p) => p.is_default) ?? items[0])!.id
    }
  },
  { immediate: true },
)
const profileOptions = computed(
  () => profiles.data.value?.items.map((p) => ({ value: p.id as number | null, label: p.name })) ?? [],
)

const sse = useSse<StreamEvent>()
const analysis = ref<AnalysisResult | null>(null)
const analysisId = ref<number | null>(null)
const markdown = ref('')
const fromCache = ref(false)
let retryTimer: ReturnType<typeof setTimeout> | null = null

const cachedStages = computed(() =>
  sse.events.value.flatMap((e) => (e.type === 'status' && e.cache ? [e.stage] : [])),
)
const streamError = computed(() => {
  const err = sse.error.value
  if (!err) return ''
  if (err.code === 'in_progress') return copy.analyze.inProgress
  if (err.code === 'llm_unavailable') return copy.llm.unavailable
  if (err.code === 'stream_interrupted') return copy.common.streamInterrupted
  return err.status ? generalMessage(err) : err.message || copy.common.unknownError
})

async function analyze() {
  if (profileId.value === null) return
  if (retryTimer) clearTimeout(retryTimer)
  await sse.start(`/bids/${bidId.value}/analyze`, { profile_id: profileId.value })
  const result = sse.events.value.find((e) => e.type === 'result')
  if (result && result.type === 'result') {
    analysis.value = result.analysis
    analysisId.value = result.analysis_id
    markdown.value = result.markdown
    fromCache.value = result.from_cache
    void queryClient.invalidateQueries({ queryKey: ['bid', bidId.value] })
    void queryClient.invalidateQueries({ queryKey: ['analyses'] })
  } else if (sse.error.value?.code === 'in_progress') {
    retryTimer = setTimeout(() => void analyze(), IN_PROGRESS_RETRY_MS) // 화면이 몇 초 뒤 다시 요청(§6.4)
  }
}
onBeforeUnmount(() => retryTimer && clearTimeout(retryTimer))

// 내 기록에서 연 분석(?analysis=) 또는 이 공고의 내 최근 분석을 보여 준다.
async function loadSaved(id: number) {
  try {
    const a = await libraryApi.analysis(id)
    analysis.value = a.analysis
    analysisId.value = a.analysis_id
    markdown.value = a.markdown
    fromCache.value = true
  } catch {
    // 기록이 지워졌으면 새로 분석하면 된다
  }
}
// 내 분석이 없으면 팀원이 팀 프로필로 만든 분석을 보여 준다 (§13 P6).
const fromTeam = ref(false)
watch(
  [() => route.query.analysis, () => bid.value?.my_analysis_id, bidId, () => bid.value?.team_analysis_id],
  ([q, mine, , team], old) => {
    if (old && old[2] !== bidId.value) analysis.value = null
    const id = Number(q) || mine || team
    fromTeam.value = !Number(q) && !mine && !!team
    if (id && id !== analysisId.value) void loadSaved(id)
  },
  { immediate: true },
)

const noText = computed(() => analysis.value?.warnings?.includes(copy.analyze.noTextMarker) ?? false)

async function copyMarkdown() {
  try {
    await navigator.clipboard.writeText(markdown.value)
    ui.toast(copy.detail.copied, 'success')
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  }
}

// ---------- 북마크 ----------
async function toggleBookmark() {
  if (!bid.value) return
  try {
    if (bid.value.bookmarked) await bidsApi.unbookmark(bid.value.bid_id)
    else await bidsApi.bookmark(bid.value.bid_id, '', analysisId.value)
    ui.toast(bid.value.bookmarked ? copy.bid.unbookmarked : copy.bid.bookmarked, 'success')
    await detail.refetch()
    void queryClient.invalidateQueries({ queryKey: ['bookmarks'] })
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  }
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <form class="flex flex-wrap items-end gap-2" @submit.prevent="lookup">
      <div class="flex flex-col gap-1.5">
        <label for="bid-no" class="text-sm font-medium text-text-2">{{ copy.detail.lookupLabel }}</label>
        <input
          id="bid-no"
          v-model="bidNo"
          name="bid_no"
          maxlength="40"
          class="h-10 w-72 max-w-full rounded-control border border-border-input bg-surface px-3 text-base"
          :aria-describedby="lookupError ? 'bid-no-hint bid-no-error' : 'bid-no-hint'"
        />
      </div>
      <UiButton type="submit" variant="secondary">{{ copy.detail.lookupSubmit }}</UiButton>
      <p id="bid-no-hint" class="w-full text-sm text-text-3">{{ copy.detail.lookupHint }}</p>
      <p v-if="lookupError" id="bid-no-error" class="w-full text-sm text-danger-fg" role="alert">
        {{ lookupError }}
      </p>
    </form>

    <UiSkeleton v-if="detail.isPending.value" :lines="3" />
    <EmptyState v-else-if="notFound" :title="copy.detail.notFound" />
    <div v-else-if="detail.isError.value" class="flex flex-col items-start gap-2" role="alert">
      <p class="text-danger-fg">{{ copy.common.unknownError }}</p>
      <UiButton variant="secondary" size="sm" @click="detail.refetch()">{{ copy.common.retry }}</UiButton>
    </div>

    <template v-else-if="bid">
      <header
        class="grid grid-cols-[4.75rem_minmax(0,1fr)] gap-x-4 gap-y-3 rounded-card border border-border bg-surface p-4 sm:grid-cols-[6rem_minmax(0,1fr)] sm:p-5"
      >
        <DeadlineStamp :deadline-at="bid.deadline_at" class="row-span-4 pt-1" />
        <div class="flex flex-wrap items-center gap-1.5">
          <UiBadge :tone="bid.source === 'prespec' ? 'primary' : 'neutral'">
            {{ bid.source === 'prespec' ? copy.bid.prespec : copy.bid.regular }}
          </UiBadge>
          <UiBadge v-if="bid.revision > 1" tone="warning">{{ copy.bid.revised }}</UiBadge>
          <UiBadge v-if="bid.cancelled" tone="danger">{{ copy.bid.cancelled }}</UiBadge>
          <span class="text-sm tabular text-text-3">{{ bid.bid_no }}</span>
        </div>
        <h2 class="text-xl font-semibold leading-snug tracking-tight text-text sm:text-2xl">{{ bid.title }}</h2>
        <div class="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-base text-text-2">
          <span>{{ bid.org_name || copy.bid.noOrg }}</span>
          <MoneyText :value="bid.budget" class="font-medium text-text" />
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="inline-flex size-10 items-center justify-center rounded-control border border-border-input hover:bg-surface-2"
            :aria-label="bid.bookmarked ? copy.bid.bookmarkRemove : copy.bid.bookmarkAdd"
            :aria-pressed="bid.bookmarked"
            @click="toggleBookmark"
          >
            <BookmarkCheck v-if="bid.bookmarked" class="size-5 text-primary" aria-hidden="true" />
            <Bookmark v-else class="size-5" aria-hidden="true" />
          </button>
          <a
            v-if="bid.detail_url"
            :href="bid.detail_url"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex h-10 items-center gap-1 px-2 text-base text-text-2 hover:underline"
          >
            {{ copy.bid.original }}<ExternalLink class="size-4" aria-hidden="true" />
          </a>
          <RouterLink
            v-if="bid.related_bid_id"
            :to="`/bids/${bid.related_bid_id}`"
            class="inline-flex h-10 items-center px-2 text-base text-primary-hover hover:underline"
          >
            {{ bid.source === 'prespec' ? copy.bid.relatedRegular : copy.bid.relatedPrespec }}
          </RouterLink>
        </div>
      </header>

      <OfficialFacts v-if="bid.official" :facts="bid.official" :doc-budgets="bid.doc_budgets" />

      <section>
        <h3 class="mb-2 text-lg font-semibold">{{ copy.detail.files }}</h3>
        <FileList :files="bid.files" :downloading="downloading" @preview="openPreview" @download="download" />
      </section>

      <section class="rounded-card border border-border bg-surface p-4">
        <h3 class="mb-2 text-lg font-semibold">{{ copy.detail.summary }}</h3>
        <template v-if="bid.summary">
          <p class="mb-3 text-sm text-text-3">{{ copy.official.aiNote }}</p>
          <p class="mb-2 font-medium">{{ bid.summary.headline }}</p>
          <p class="whitespace-pre-line text-base text-text-2">{{ bid.summary.overview }}</p>
          <SummaryFacts :summary="bid.summary" />
        </template>
        <p v-else class="text-base text-text-3">{{ copy.detail.summaryHint }}</p>
      </section>

      <section class="flex flex-col gap-3 rounded-card border border-border bg-surface p-4">
        <h3 class="text-lg font-semibold">{{ copy.detail.analyzeTitle }}</h3>
        <template v-if="profiles.data.value && !profiles.data.value.items.length">
          <p class="text-base text-text-2">{{ copy.detail.profileRequired }}</p>
          <RouterLink to="/settings/profiles" class="font-medium text-primary-hover hover:underline">
            {{ copy.detail.goSettings }}
          </RouterLink>
        </template>
        <div v-else class="flex flex-wrap items-end gap-3">
          <div class="w-64">
            <UiSelect v-model="profileId" :label="copy.recommend.profile" :options="profileOptions" />
          </div>
          <UiButton :loading="sse.streaming.value" :disabled="profileId === null" @click="analyze">
            {{ copy.detail.analyzeSubmit }}
          </UiButton>
        </div>
        <ProgressSteps
          v-if="sse.streaming.value || sse.events.value.some((e) => e.type === 'status')"
          :stages="[...STAGES]"
          :current="sse.streaming.value ? sse.stage.value : null"
          :cached="cachedStages"
        />
        <div v-if="streamError" class="flex flex-col items-start gap-2" role="alert">
          <p class="text-base text-danger-fg">{{ streamError }}</p>
          <UiButton
            v-if="sse.error.value?.code !== 'in_progress'"
            variant="secondary"
            size="sm"
            @click="analyze"
          >{{ copy.common.retry }}</UiButton>
        </div>
      </section>

      <section v-if="analysis" class="flex flex-col gap-4">
        <p
          v-if="noText"
          class="rounded-card border border-warning-fg/30 bg-warning-bg px-4 py-3 text-base text-warning-fg"
          role="note"
        >
          {{ copy.analyze.noText }}
        </p>
        <p v-if="fromTeam" class="rounded-control bg-primary-soft px-3 py-2 text-sm text-primary-hover">{{ copy.detail.teamAnalysis }}</p>
        <p v-else-if="fromCache" class="text-sm text-text-3">{{ copy.analysis.fromCache }}</p>
        <div class="rounded-card border border-border bg-surface p-4">
          <AnalysisResultView :analysis="analysis" />
        </div>
        <div class="flex flex-wrap gap-2">
          <UiButton variant="secondary" size="sm" @click="copyMarkdown">
            <Copy class="size-4" aria-hidden="true" />{{ copy.detail.copyMarkdown }}
          </UiButton>
        </div>
        <FeedbackButtons v-if="analysisId" target-type="analysis" :target-id="analysisId" />
      </section>
    </template>

    <UiDrawer
      v-model:open="previewOpen"
      :title="preview?.name ?? ''"
      :description="preview?.truncated ? copy.detail.previewTruncated : undefined"
    >
      <pre class="whitespace-pre-wrap break-words font-sans text-sm text-text">{{ preview?.text }}</pre>
    </UiDrawer>
  </div>
</template>

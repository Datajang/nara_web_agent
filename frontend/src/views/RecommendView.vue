<script setup lang="ts">
// 맞춤 추천 (SPEC §7.4). 프로필 필수, status(score)의 progress로 진행 막대, 점수 내림차순 카드.
import { useQuery } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { profilesApi } from '@/api/profiles'
import type { BidCard, StreamEvent } from '@/api/types'
import BidList from '@/components/bid/BidList.vue'
import ProgressSteps from '@/components/bid/ProgressSteps.vue'
import ChipInput from '@/components/ui/ChipInput.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSegmented from '@/components/ui/UiSegmented.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useBookmarkToggle } from '@/composables/useBookmarkToggle'
import { useSse } from '@/composables/useSse'
import { copy } from '@/copy'
import { generalMessage } from '@/utils/authErrors'

const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => profilesApi.list() })
const profileId = ref<number | null>(null)
const days = ref<7 | 14 | 30>(14)
const source = ref<'all' | 'regular' | 'prespec'>('all')
const topN = ref<10 | 20 | 30>(20)
const keywords = ref<string[]>([])
const chips = ref<InstanceType<typeof ChipInput> | null>(null)
const sse = useSse<StreamEvent>()
const cards = ref<BidCard[]>([])
const ran = ref(false)

watch(
  () => profiles.data.value?.items,
  (items) => {
    if (items?.length && !items.some((p) => p.id === profileId.value)) {
      profileId.value = (items.find((p) => p.is_default) ?? items[0])!.id
    }
  },
  { immediate: true },
)

const progress = computed(() => {
  const last = [...sse.events.value]
    .reverse()
    .find((e) => e.type === 'status' && e.stage === 'score' && e.progress)
  return last && last.type === 'status' ? last.progress : null
})
const cachedScore = computed(() => {
  const done = sse.events.value.find((e) => e.type === 'done')
  return done?.type === 'done' && done.usage.cache.score === true
})
const errorText = computed(() => {
  const err = sse.error.value
  if (!err) return ''
  if (err.code === 'llm_unavailable') return copy.llm.unavailable
  if (err.code === 'stream_interrupted') return copy.common.streamInterrupted
  return err.status ? generalMessage(err) : copy.common.unknownError
})

async function run() {
  if (profileId.value === null) return
  chips.value?.commit()
  ran.value = true
  cards.value = []
  await sse.start('/recommend', {
    profile_id: profileId.value,
    days: days.value,
    source: source.value,
    top_n: topN.value,
    keywords: keywords.value.length ? keywords.value : null,
  })
  const ev = sse.events.value.find((e) => e.type === 'cards')
  if (ev?.type === 'cards') cards.value = ev.items
}
const toggleBookmark = useBookmarkToggle(cards)
</script>

<template>
  <div class="flex flex-col gap-4">
    <UiSkeleton v-if="profiles.isPending.value" :lines="2" />
    <EmptyState v-else-if="!profiles.data.value?.items.length" :title="copy.recommend.noProfile">
      <template #action>
        <RouterLink
          to="/settings/profiles"
          class="inline-flex h-10 items-center rounded-control bg-primary px-4 font-medium text-white hover:bg-primary-hover"
        >{{ copy.recommend.makeProfile }}</RouterLink>
      </template>
    </EmptyState>

    <template v-else>
      <form
        class="grid gap-4 rounded-card border border-border bg-surface p-4 md:grid-cols-2"
        :aria-label="copy.recommend.formLabel"
        @submit.prevent="run"
      >
        <UiSelect
          v-model="profileId"
          :label="copy.recommend.profile"
          :options="profiles.data.value.items.map((p) => ({ value: p.id as number | null, label: p.name }))"
        />
        <UiSelect
          v-model="source"
          :label="copy.search.source"
          :options="[
            { value: 'all', label: copy.search.sourceAll },
            { value: 'regular', label: copy.bid.regular },
            { value: 'prespec', label: copy.bid.prespec },
          ]"
        />
        <UiSegmented
          v-model="days"
          :label="copy.recommend.days"
          :options="[7, 14, 30].map((d) => ({ value: d as 7 | 14 | 30, label: copy.search.recentDays(d) }))"
        />
        <UiSegmented
          v-model="topN"
          :label="copy.recommend.topN"
          :options="[10, 20, 30].map((n) => ({ value: n as 10 | 20 | 30, label: copy.recommend.topNOption(n) }))"
        />
        <div class="md:col-span-2">
          <ChipInput
            ref="chips"
            v-model="keywords"
            :label="copy.recommend.keywords"
            :hint="copy.recommend.keywordsHint"
          />
        </div>
        <div class="md:col-span-2">
          <UiButton type="button" :loading="sse.streaming.value" @click="run">{{ copy.recommend.submit }}</UiButton>
        </div>
      </form>

      <div v-if="sse.streaming.value || progress" class="flex flex-col gap-2">
        <ProgressSteps :stages="['search', 'score']" :current="sse.streaming.value ? sse.stage.value : null" />
        <div v-if="progress" class="flex items-center gap-3">
          <div
            role="progressbar"
            :aria-label="copy.recommend.progressLabel"
            :aria-valuenow="progress.done"
            aria-valuemin="0"
            :aria-valuemax="progress.total"
            class="h-2 flex-1 overflow-hidden rounded-full bg-surface-2"
          >
            <div
              class="h-full bg-primary transition-[width]"
              :style="{ width: `${progress.total ? (100 * progress.done) / progress.total : 0}%` }"
            />
          </div>
          <span class="text-sm tabular text-text-2">{{ copy.recommend.progress(progress.done, progress.total) }}</span>
        </div>
      </div>

      <div v-if="errorText" class="flex flex-col items-start gap-2" role="alert">
        <p class="text-danger-fg">{{ errorText }}</p>
        <UiButton variant="secondary" size="sm" @click="run">{{ copy.common.retry }}</UiButton>
      </div>
      <p v-if="cachedScore" class="text-sm text-text-3">{{ copy.recommend.cached }}</p>
      <EmptyState v-if="ran && !sse.streaming.value && !errorText && !cards.length" :title="copy.recommend.empty" />
      <BidList v-if="cards.length" :bids="cards" show-score @toggle-bookmark="toggleBookmark" />
    </template>
  </div>
</template>

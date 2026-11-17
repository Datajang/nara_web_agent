<script setup lang="ts">
// 맞춤 추천 (SPEC §7.4). 프로필 필수, status(score)의 progress로 진행 막대, 점수 내림차순 카드.
// 조건·진행·결과는 스토어에 있어 다른 화면에 다녀와도 그대로이고, 새로고침하면 마지막 추천 기록을 불러온다.
import { useQuery } from '@tanstack/vue-query'
import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { profilesApi } from '@/api/profiles'
import BidList from '@/components/bid/BidList.vue'
import ProgressSteps from '@/components/bid/ProgressSteps.vue'
import ChipInput from '@/components/ui/ChipInput.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSegmented from '@/components/ui/UiSegmented.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useBookmarkToggle } from '@/composables/useBookmarkToggle'
import { copy } from '@/copy'
import { useAuthStore } from '@/stores/auth'
import { CANDIDATE_OPTIONS, DAY_OPTIONS, useRecommendStore } from '@/stores/recommend'
import { generalMessage } from '@/utils/authErrors'
import { formatDateTime } from '@/utils/format'

const auth = useAuthStore()
const store = useRecommendStore()
const {
  profileId,
  days,
  source,
  candidates,
  keywords,
  includeSmall,
  events,
  stage,
  streaming,
  error,
  cards,
  ran,
  restoredAt,
} = storeToRefs(store)
if (auth.me) void store.ensureFor(auth.me.id)

const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => profilesApi.list() })
const chips = ref<InstanceType<typeof ChipInput> | null>(null)

// 선택한(또는 기록에서 불러온) 프로필이 없어졌으면 기본 프로필로
watch(
  [() => profiles.data.value?.items, profileId],
  ([items]) => {
    if (items?.length && !items.some((p) => p.id === profileId.value)) {
      profileId.value = (items.find((p) => p.is_default) ?? items[0])!.id
    }
  },
  { immediate: true },
)

const progress = computed(() => {
  const last = [...events.value]
    .reverse()
    .find((e) => e.type === 'status' && e.stage === 'score' && e.progress)
  return last && last.type === 'status' ? last.progress : null
})
const cachedScore = computed(() => {
  const done = events.value.find((e) => e.type === 'done')
  return done?.type === 'done' && done.usage.cache.score === true
})
const errorText = computed(() => {
  const err = error.value
  if (!err) return ''
  if (err.code === 'llm_unavailable') return copy.llm.unavailable
  if (err.code === 'stream_interrupted') return copy.common.streamInterrupted
  return err.status ? generalMessage(err) : copy.common.unknownError
})

function run() {
  chips.value?.commit()
  void store.run()
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
          :options="DAY_OPTIONS.map((d) => ({ value: d, label: copy.search.recentDays(d) }))"
        />
        <div class="flex flex-col gap-1">
          <UiSegmented
            v-model="candidates"
            :label="copy.recommend.candidates"
            :options="CANDIDATE_OPTIONS.map((n) => ({ value: n, label: copy.recommend.candidatesOption(n) }))"
          />
          <p class="text-sm text-text-3">{{ copy.recommend.candidatesHint }}</p>
        </div>
        <div class="md:col-span-2">
          <ChipInput
            ref="chips"
            v-model="keywords"
            :label="copy.recommend.keywords"
            :hint="copy.recommend.keywordsHint"
          />
        </div>
        <label class="inline-flex items-center gap-2 text-sm text-text-2 md:col-span-2">
          <input v-model="includeSmall" name="recommend-small" type="checkbox" class="size-4" />
          {{ copy.recommend.includeSmall }}
          <span v-if="!includeSmall" class="text-text-3">{{ copy.recommend.minBudgetNote }}</span>
        </label>
        <div class="md:col-span-2">
          <UiButton type="button" :loading="streaming" @click="run">{{ copy.recommend.submit }}</UiButton>
        </div>
      </form>

      <div v-if="streaming || progress" class="flex flex-col gap-2">
        <ProgressSteps :stages="['search', 'score']" :current="streaming ? stage : null" />
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
      <p v-if="restoredAt && !streaming" class="text-sm text-text-3">
        {{ copy.recommend.restored(formatDateTime(restoredAt)) }}
      </p>
      <EmptyState v-if="ran && !streaming && !errorText && !cards.length" :title="copy.recommend.empty" />
      <BidList v-if="cards.length" :bids="cards" show-score @toggle-bookmark="toggleBookmark" />
    </template>
  </div>
</template>

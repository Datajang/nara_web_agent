<script setup lang="ts">
// 마감 보드의 공고 카드 (2026-11-18, 시안 D). 위: D-n·마감 시각 | 예산, 제목 링크, 기관, 꼬리표,
// 아래: 맞은 키워드 | 북마크·원문·분석. 어시스턴트 옆 칸에서도 쓴다(맞은 키워드 없음, 북마크 숨김 가능). 칸 폭이 좁아 제목은 세 줄까지. 텍스트는 바인딩으로만 렌더(XSS 방어).
import BookmarkIcon from '@/components/bid/BookmarkIcon.vue'
import { ExternalLink } from 'lucide-vue-next'
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { BidCard } from '@/api/types'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'
import { formatDateTime, formatDday, formatShortDate } from '@/utils/format'
import MoneyText from './MoneyText.vue'
import { deadlineTone } from './tones'

type Card = BidCard & { matched_keywords?: string[] }
const props = withDefaults(defineProps<{ bid: Card; now?: Date; bookmarkable?: boolean }>(), {
  now: undefined,
  bookmarkable: true,
})
const emit = defineEmits<{ 'toggle-bookmark': [Card] }>()
const now = computed(() => props.now ?? new Date())
const toneClass = computed(
  () =>
    ({ danger: 'text-danger-fg', warning: 'text-warning-fg' })[
      deadlineTone(props.bid.deadline_at, now.value) as 'danger' | 'warning'
    ] ?? 'text-text',
)
</script>

<template>
  <article
    class="flex flex-col gap-2 rounded-card border border-border bg-surface px-4 py-3.5 transition-shadow hover:border-border-input hover:shadow-card"
  >
    <p class="flex items-center justify-between gap-2 text-sm">
      <span
        class="font-semibold tabular"
        :class="toneClass"
        :title="bid.deadline_at ? formatDateTime(bid.deadline_at) : undefined"
      >
        {{ formatDday(bid.deadline_at, now) }}<template v-if="bid.deadline_at">
          · {{ formatShortDate(bid.deadline_at) }}</template
        >
      </span>
      <MoneyText :value="bid.budget" class="shrink-0 text-md font-semibold text-text" />
    </p>
    <h3 class="text-base font-semibold leading-snug text-text">
      <RouterLink
        :to="`/bids/${bid.bid_id}`"
        class="line-clamp-3 decoration-primary/40 underline-offset-4 hover:text-primary hover:underline"
      >{{ bid.title }}</RouterLink>
    </h3>
    <p class="truncate text-xs text-text-3">{{ bid.org_name || copy.bid.noOrg }}</p>
    <p class="flex flex-wrap items-center gap-1">
      <UiBadge :tone="bid.source === 'prespec' ? 'primary' : 'neutral'">
        {{ bid.source === 'prespec' ? copy.bid.prespec : copy.bid.regular }}
      </UiBadge>
      <UiBadge v-if="bid.revision > 1" tone="warning">{{ copy.bid.revised }}</UiBadge>
      <UiBadge v-if="bid.summary_ready" tone="success">{{ copy.bid.summaryReady }}</UiBadge>
    </p>
    <div class="mt-0.5 flex items-center justify-between gap-2 border-t border-border pt-2">
      <p class="flex min-w-0 flex-wrap gap-x-1.5 text-xs text-text-3">
        <span class="sr-only">{{ copy.feed.matched }}</span>
        <span v-for="k in bid.matched_keywords" :key="k"><span aria-hidden="true">#</span><span data-matched>{{ k }}</span></span>
      </p>
      <span class="flex shrink-0 items-center">
        <button
          v-if="bookmarkable"
          type="button"
          class="inline-flex size-8 items-center justify-center rounded-control text-text-2 hover:bg-surface-2 hover:text-text"
          :aria-label="bid.bookmarked ? copy.bid.bookmarkRemove : copy.bid.bookmarkAdd"
          :aria-pressed="bid.bookmarked"
          @click="emit('toggle-bookmark', bid)"
        >
          <BookmarkIcon :on="bid.bookmarked" class="size-4" />
        </button>
        <a
          v-if="bid.detail_url"
          :href="bid.detail_url"
          target="_blank"
          rel="noopener noreferrer"
          :aria-label="copy.bid.originalNewTab"
          :title="copy.bid.originalNewTab"
          class="inline-flex size-8 items-center justify-center rounded-control text-text-2 hover:bg-surface-2 hover:text-text"
        >
          <ExternalLink class="size-3.5" aria-hidden="true" />
        </a>
        <RouterLink
          :to="`/bids/${bid.bid_id}`"
          class="ml-1 inline-flex h-8 items-center rounded-control border border-border-input px-3 text-sm font-medium text-text hover:border-primary hover:text-primary"
        >{{ copy.bid.analyze }}</RouterLink>
      </span>
    </div>
  </article>
</template>

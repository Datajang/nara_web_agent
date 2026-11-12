<script setup lang="ts">
// 공고 카드 (SPEC §7.3, §10.4, P7 공고 대장 형식). 클릭 영역은 제목 링크 하나. 텍스트는 바인딩으로만 렌더(XSS 방어).
import { Bookmark, BookmarkCheck, ExternalLink } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import type { BidCard } from '@/api/types'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'
import DeadlineStamp from './DeadlineStamp.vue'
import MoneyText from './MoneyText.vue'
import ScoreBadge from './ScoreBadge.vue'

withDefaults(defineProps<{ bid: BidCard; showScore?: boolean; compact?: boolean }>(), {
  showScore: false,
  compact: false,
})
const emit = defineEmits<{ 'toggle-bookmark': [BidCard] }>()
</script>

<template>
  <!-- 공고 대장의 한 줄: 왼쪽 마감 칸 | 제목·기관·예산·꼬리표 | 동작. 목록에서는 줄끼리 가는 선으로 나뉜다(BidList). -->
  <article
    class="grid grid-cols-[4.75rem_minmax(0,1fr)] gap-x-4 gap-y-2 bg-surface px-4 py-4 sm:grid-cols-[6rem_minmax(0,1fr)_auto] sm:px-5"
    :class="compact ? 'rounded-card border border-border' : ''"
  >
    <DeadlineStamp :deadline-at="bid.deadline_at" class="pt-0.5" />
    <div class="flex min-w-0 flex-col gap-1.5">
      <h3 class="text-md font-semibold leading-snug text-text">
        <RouterLink
          :to="`/bids/${bid.bid_id}`"
          class="line-clamp-2 decoration-primary/40 underline-offset-4 hover:text-primary hover:underline"
        >{{ bid.title }}</RouterLink>
      </h3>
      <p class="flex flex-wrap items-baseline gap-x-4 gap-y-0.5 text-sm text-text-2">
        <span>{{ bid.org_name || copy.bid.noOrg }}</span>
        <MoneyText :value="bid.budget" class="font-medium text-text" />
      </p>
      <p class="flex flex-wrap items-center gap-1">
        <UiBadge :tone="bid.source === 'prespec' ? 'primary' : 'neutral'">
          {{ bid.source === 'prespec' ? copy.bid.prespec : copy.bid.regular }}
        </UiBadge>
        <UiBadge v-if="bid.revision > 1" tone="warning">{{ copy.bid.revised }}</UiBadge>
        <UiBadge v-if="bid.cancelled" tone="danger">{{ copy.bid.cancelled }}</UiBadge>
        <UiBadge v-if="bid.summary_ready" tone="success">{{ copy.bid.summaryReady }}</UiBadge>
        <ScoreBadge v-if="showScore && bid.score != null" :score="bid.score" />
      </p>
      <p v-if="showScore && bid.reason" class="text-sm text-text-2">{{ bid.reason }}</p>
      <slot />
    </div>
    <div
      v-if="!compact"
      class="col-start-2 flex items-center gap-1 sm:col-start-3 sm:row-start-1 sm:self-start"
    >
      <span class="flex items-center">
        <button
          type="button"
          class="inline-flex size-9 items-center justify-center rounded-control text-text-2 hover:bg-surface-2 hover:text-text"
          :aria-label="bid.bookmarked ? copy.bid.bookmarkRemove : copy.bid.bookmarkAdd"
          :aria-pressed="bid.bookmarked"
          @click="emit('toggle-bookmark', bid)"
        >
          <BookmarkCheck v-if="bid.bookmarked" class="size-5 text-primary" aria-hidden="true" />
          <Bookmark v-else class="size-5" aria-hidden="true" />
        </button>
        <a
          v-if="bid.detail_url"
          :href="bid.detail_url"
          target="_blank"
          rel="noopener noreferrer"
          :aria-label="copy.bid.originalNewTab"
          :title="copy.bid.originalNewTab"
          class="inline-flex h-9 items-center gap-1 rounded-control px-2 text-sm text-text-2 hover:bg-surface-2 hover:text-text"
        >
          {{ copy.bid.original }}<ExternalLink class="size-3.5" aria-hidden="true" />
        </a>
      </span>
      <RouterLink
        :to="`/bids/${bid.bid_id}`"
        class="ml-1 inline-flex h-8 items-center rounded-control border border-border-input px-3 text-sm font-medium text-text hover:border-primary hover:text-primary"
      >{{ copy.bid.analyze }}</RouterLink>
    </div>
  </article>
</template>

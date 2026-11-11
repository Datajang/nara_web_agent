<script setup lang="ts">
// 공고 카드 (SPEC §7.3, §10.4). 클릭 영역은 제목 링크 하나. 텍스트는 바인딩으로만 렌더(XSS 방어).
import { Bookmark, BookmarkCheck, ExternalLink } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import type { BidCard } from '@/api/types'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'
import DeadlineBadge from './DeadlineBadge.vue'
import MoneyText from './MoneyText.vue'
import ScoreBadge from './ScoreBadge.vue'

withDefaults(defineProps<{ bid: BidCard; showScore?: boolean; compact?: boolean }>(), {
  showScore: false,
  compact: false,
})
const emit = defineEmits<{ 'toggle-bookmark': [BidCard] }>()
</script>

<template>
  <article class="flex flex-col gap-2 rounded-card border border-border bg-surface p-4">
    <div class="flex flex-wrap items-center gap-1.5">
      <UiBadge :tone="bid.source === 'prespec' ? 'primary' : 'neutral'">
        {{ bid.source === 'prespec' ? copy.bid.prespec : copy.bid.regular }}
      </UiBadge>
      <UiBadge v-if="bid.revision > 1" tone="warning">{{ copy.bid.revised }}</UiBadge>
      <UiBadge v-if="bid.cancelled" tone="danger">{{ copy.bid.cancelled }}</UiBadge>
      <UiBadge v-if="bid.summary_ready" tone="success">{{ copy.bid.summaryReady }}</UiBadge>
      <ScoreBadge v-if="showScore && bid.score != null" :score="bid.score" />
    </div>
    <h3 class="text-lg font-semibold leading-snug text-text">
      <RouterLink
        :to="`/bids/${bid.bid_id}`"
        class="line-clamp-2 hover:text-primary-hover hover:underline"
      >{{ bid.title }}</RouterLink>
    </h3>
    <p v-if="showScore && bid.reason" class="text-sm text-text-2">{{ bid.reason }}</p>
    <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-text-2">
      <span>{{ bid.org_name || copy.bid.noOrg }}</span>
      <MoneyText :value="bid.budget" />
      <DeadlineBadge :deadline-at="bid.deadline_at" />
    </div>
    <div v-if="!compact" class="mt-1 flex flex-wrap items-center gap-2">
      <button
        type="button"
        class="inline-flex size-10 items-center justify-center rounded-control text-text-2 hover:bg-surface-2"
        :aria-label="bid.bookmarked ? copy.bid.bookmarkRemove : copy.bid.bookmarkAdd"
        :aria-pressed="bid.bookmarked"
        @click="emit('toggle-bookmark', bid)"
      >
        <BookmarkCheck v-if="bid.bookmarked" class="size-5 text-primary" aria-hidden="true" />
        <Bookmark v-else class="size-5" aria-hidden="true" />
      </button>
      <RouterLink
        :to="`/bids/${bid.bid_id}`"
        class="inline-flex h-8 items-center rounded-control border border-border-input px-3 text-sm font-medium text-text hover:bg-surface-2"
      >{{ copy.bid.analyze }}</RouterLink>
      <a
        v-if="bid.detail_url"
        :href="bid.detail_url"
        target="_blank"
        rel="noopener noreferrer"
        :aria-label="copy.bid.originalNewTab"
        class="inline-flex h-8 items-center gap-1 px-2 text-sm text-text-2 hover:text-text hover:underline"
      >
        {{ copy.bid.original }}
        <ExternalLink class="size-3.5" aria-hidden="true" />
      </a>
    </div>
  </article>
</template>

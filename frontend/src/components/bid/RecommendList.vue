<script setup lang="ts">
// 맞춤 추천 결과 목록 (2026-11-18, 시안 D 적용). 왼쪽 칸에 적합도 숫자를 크게(막대 없이, 사용자 요청),
// 가운데 공고와 추천 이유 상자, 오른쪽에 마감·예산·동작. 좁으면 점수|본문 두 칸으로 접힌다.

import BookmarkIcon from '@/components/bid/BookmarkIcon.vue'
import { RouterLink } from 'vue-router'
import type { BidCard } from '@/api/types'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'
import DeadlineStamp from './DeadlineStamp.vue'
import MoneyText from './MoneyText.vue'
import { scoreTone } from './tones'

defineProps<{ bids: BidCard[] }>()
const emit = defineEmits<{ 'toggle-bookmark': [BidCard] }>()

const toneText = { success: 'text-success-fg', primary: 'text-primary', neutral: 'text-text-2' } as Record<string, string>
const label = (n: number) => (n >= 80 ? copy.score.high : n >= 60 ? copy.score.mid : copy.score.low)
const grid =
  'grid grid-cols-[4rem_minmax(0,1fr)] gap-x-5 gap-y-2 px-4 sm:px-5 md:grid-cols-[4.5rem_minmax(0,1fr)_6.5rem_6.5rem_auto]'
</script>

<template>
  <section :aria-label="copy.recommend.listLabel" class="overflow-hidden rounded-card border border-border bg-surface">
    <div :class="grid" class="hidden bg-surface-2 py-2.5 text-xs font-semibold text-text-3 md:grid" aria-hidden="true">
      <span>{{ copy.recommend.colScore }}</span>
      <span>{{ copy.recommend.colBid }}</span>
      <span>{{ copy.bid.deadline }}</span>
      <span class="text-right">{{ copy.bid.budget }}</span>
      <span />
    </div>
    <ul class="divide-y divide-border">
      <li v-for="b in bids" :key="b.bid_id">
        <article :class="grid" class="py-4">
          <div class="flex flex-col gap-0.5 pt-0.5" :title="copy.score.tooltip" data-score>
            <template v-if="b.score != null">
              <span class="text-2xl font-bold leading-none tabular" :class="toneText[scoreTone(b.score)]">{{ b.score }}</span>
              <span class="text-xs text-text-3">{{ label(b.score) }}</span>
            </template>
          </div>
          <div class="flex min-w-0 flex-col gap-1.5">
            <h3 class="text-md font-semibold leading-snug text-text">
              <RouterLink
                :to="`/bids/${b.bid_id}`"
                class="decoration-primary/40 underline-offset-4 hover:text-primary hover:underline"
              >{{ b.title }}</RouterLink>
            </h3>
            <p class="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-text-2">
              <span>{{ b.org_name || copy.bid.noOrg }}</span>
              <UiBadge :tone="b.source === 'prespec' ? 'primary' : 'neutral'">
                {{ b.source === 'prespec' ? copy.bid.prespec : copy.bid.regular }}
              </UiBadge>
              <UiBadge v-if="b.summary_ready" tone="success">{{ copy.bid.summaryReady }}</UiBadge>
              <MoneyText :value="b.budget" class="font-medium text-text md:hidden" />
            </p>
            <p v-if="b.reason" class="mt-0.5 rounded-control bg-surface-2 px-3 py-2 text-sm leading-relaxed text-text-2">
              {{ b.reason }}
            </p>
          </div>
          <DeadlineStamp :deadline-at="b.deadline_at" class="col-start-2 md:col-start-auto" />
          <MoneyText :value="b.budget" class="hidden pt-1 text-right text-md font-semibold text-text md:block" />
          <div class="col-start-2 flex items-start gap-1 md:col-start-auto">
            <button
              type="button"
              class="inline-flex size-9 items-center justify-center rounded-control text-text-2 hover:bg-surface-2 hover:text-text"
              :aria-label="b.bookmarked ? copy.bid.bookmarkRemove : copy.bid.bookmarkAdd"
              :aria-pressed="b.bookmarked"
              @click="emit('toggle-bookmark', b)"
            >
              <BookmarkIcon :on="b.bookmarked" class="size-5" />
            </button>
            <RouterLink
              :to="`/bids/${b.bid_id}`"
              class="inline-flex h-9 items-center rounded-control border border-border-input px-3 text-sm font-medium text-text hover:border-primary hover:text-primary"
            >{{ copy.bid.analyze }}</RouterLink>
          </div>
        </article>
      </li>
    </ul>
  </section>
</template>

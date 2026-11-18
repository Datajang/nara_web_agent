<script setup lang="ts">
// 관심 공고 마감 보드 (2026-11-18, 시안 D): 오늘 마감 / 3일 안 / 7일 안 / 8일 이후 네 칸.
// 칸마다 건수와 'N건 더 보기'(그 칸에 이어 붙임). 넓으면 네 칸 한 줄, 중간 폭은 두 칸씩, 좁으면 한 칸씩 쌓인다.
// 칸 머리 색은 마감 색 규칙(§10.1, tones.ts)과 같다: 3일 이내 danger, 4~7일 warning, 그 뒤 neutral.
import type { Due, FeedItem } from '@/api/teams'
import { copy } from '@/copy'
import BidBoardCard from './BidBoardCard.vue'

export interface BoardColumn {
  due: Due
  total: number
  items: FeedItem[]
  loading: boolean
}

defineProps<{ columns: BoardColumn[]; now?: Date }>()
const emit = defineEmits<{ more: [Due]; 'toggle-bookmark': [FeedItem] }>()

const head: Record<Due, string> = {
  today: 'border-danger-fg text-danger-fg',
  d3: 'border-danger-fg text-danger-fg',
  d7: 'border-warning-fg text-warning-fg',
  later: 'border-border-input text-text',
}
</script>

<template>
  <div class="grid items-start gap-5 lg:grid-cols-2 min-[1400px]:grid-cols-4">
    <section
      v-for="c in columns"
      :key="c.due"
      :aria-labelledby="`due-${c.due}`"
      :data-due="c.due"
      class="flex min-w-0 flex-col gap-2.5"
    >
      <header class="flex items-center justify-between border-b-[3px] px-1 pb-2" :class="head[c.due]">
        <h2 :id="`due-${c.due}`" class="text-md font-bold">{{ copy.feed.due[c.due] }}</h2>
        <span class="text-sm font-semibold tabular text-text-2">{{ copy.feed.total(c.total) }}</span>
      </header>
      <ul v-if="c.items.length" class="flex flex-col gap-2.5">
        <li v-for="b in c.items" :key="b.bid_id">
          <BidBoardCard :bid="b" :now="now" @toggle-bookmark="emit('toggle-bookmark', $event as FeedItem)" />
        </li>
      </ul>
      <p v-else class="rounded-card border border-dashed border-border px-4 py-6 text-center text-sm text-text-3">
        {{ copy.feed.columnEmpty }}
      </p>
      <button
        v-if="c.items.length < c.total"
        type="button"
        data-more
        class="h-10 rounded-card border border-dashed border-border-input text-sm text-text-2 hover:border-primary hover:text-primary disabled:opacity-60"
        :disabled="c.loading"
        @click="emit('more', c.due)"
      >
        {{ copy.feed.columnMore(c.total - c.items.length) }}
      </button>
    </section>
  </div>
</template>

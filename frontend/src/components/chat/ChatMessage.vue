<script setup lang="ts">
// 말풍선 (SPEC §10.4): 사용자는 오른쪽, 도우미는 왼쪽 평탄 배경. 스트리밍 중에는 커서.
import type { BidCard as Card } from '@/api/types'
import BidCard from '@/components/bid/BidCard.vue'
import { copy } from '@/copy'

export interface ChatAction {
  name: string
  params: Record<string, unknown>
}

defineProps<{
  role: 'user' | 'assistant'
  content: string
  cards?: Card[]
  actions?: ChatAction[]
  streaming?: boolean
  status?: string | null
  error?: string | null
}>()
const emit = defineEmits<{ action: [ChatAction]; retry: []; 'toggle-bookmark': [Card] }>()

function tabName(a: ChatAction): string {
  const tab = String(a.params.tab ?? 'search') as keyof typeof copy.assistant.tabNames
  return copy.assistant.tabNames[tab] ?? copy.assistant.tabNames.search
}
</script>

<template>
  <div class="flex" :class="role === 'user' ? 'justify-end' : 'justify-start'">
    <div
      class="flex max-w-[min(680px,100%)] flex-col gap-2"
      :class="role === 'user' ? 'items-end' : 'items-start'"
    >
      <span class="sr-only">{{ role === 'user' ? copy.assistant.you : copy.assistant.bot }}</span>
      <div
        v-if="content || streaming"
        class="whitespace-pre-wrap rounded-card px-4 py-3 text-base"
        :class="role === 'user' ? 'bg-primary text-white' : 'bg-surface-2 text-text'"
      >
        {{ content }}<span
          v-if="streaming"
          class="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-text-3 align-middle motion-reduce:animate-none"
          aria-hidden="true"
        />
      </div>
      <p v-if="streaming && status" class="text-sm text-text-3" role="status">{{ status }}</p>
      <ul v-if="cards?.length" class="grid w-full gap-2">
        <li v-for="c in cards" :key="c.bid_id">
          <BidCard :bid="c" compact @toggle-bookmark="emit('toggle-bookmark', $event)" />
        </li>
      </ul>
      <div v-if="actions?.length" class="flex flex-wrap gap-2">
        <button
          v-for="(a, i) in actions"
          :key="i"
          type="button"
          class="h-8 rounded-control border border-border-input bg-surface px-3 text-sm font-medium hover:bg-surface-2"
          @click="emit('action', a)"
        >
          {{ copy.assistant.openTab(tabName(a)) }}
        </button>
      </div>
      <div v-if="error" class="flex flex-col items-start gap-2" role="alert">
        <p class="text-sm text-danger-fg">{{ error }}</p>
        <button
          type="button"
          class="h-8 rounded-control border border-border-input bg-surface px-3 text-sm font-medium hover:bg-surface-2"
          @click="emit('retry')"
        >
          {{ copy.common.retry }}
        </button>
      </div>
    </div>
  </div>
</template>

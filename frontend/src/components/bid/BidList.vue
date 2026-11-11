<script setup lang="ts">
// 카드/표 목록. 768px 미만에서는 표 대신 카드 (SPEC §10.3 모바일 표시).
import { useMediaQuery } from '@vueuse/core'
import { computed } from 'vue'
import type { BidCard as Card } from '@/api/types'
import BidCard from './BidCard.vue'
import BidTable from './BidTable.vue'

const props = withDefaults(
  defineProps<{ bids: Card[]; view?: 'cards' | 'table'; showScore?: boolean }>(),
  { view: 'cards', showScore: false },
)
const emit = defineEmits<{ 'toggle-bookmark': [Card] }>()
const narrow = useMediaQuery('(max-width: 767px)')
const asTable = computed(() => props.view === 'table' && !narrow.value)
</script>

<template>
  <BidTable v-if="asTable" :bids="bids" />
  <ul v-else class="grid gap-3">
    <li v-for="b in bids" :key="b.bid_id">
      <BidCard :bid="b" :show-score="showScore" @toggle-bookmark="emit('toggle-bookmark', $event)" />
    </li>
  </ul>
</template>

<script setup lang="ts">
// 표 보기 (SPEC §7.3, §10.4): 제목·기관·예산·마감·구분. 모바일에서는 BidList가 카드로 바꾼다.
import { RouterLink } from 'vue-router'
import type { BidCard } from '@/api/types'
import { copy } from '@/copy'
import DeadlineBadge from './DeadlineBadge.vue'
import MoneyText from './MoneyText.vue'

defineProps<{ bids: BidCard[] }>()
</script>

<template>
  <div class="overflow-hidden rounded-card border border-border bg-surface">
    <table class="w-full text-sm">
      <thead class="sticky top-0 bg-surface-2 text-left text-text-2">
        <tr>
          <th scope="col" class="px-3 py-2 font-medium">{{ copy.bid.title }}</th>
          <th scope="col" class="px-3 py-2 font-medium">{{ copy.bid.org }}</th>
          <th scope="col" class="px-3 py-2 text-right font-medium">{{ copy.bid.budget }}</th>
          <th scope="col" class="px-3 py-2 font-medium">{{ copy.bid.deadline }}</th>
          <th scope="col" class="px-3 py-2 font-medium">{{ copy.bid.source }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="b in bids" :key="b.bid_id" class="border-t border-border">
          <td class="px-3 py-2">
            <RouterLink :to="`/bids/${b.bid_id}`" class="text-text hover:underline">{{ b.title }}</RouterLink>
          </td>
          <td class="px-3 py-2 text-text-2">{{ b.org_name || copy.bid.noOrg }}</td>
          <td class="px-3 py-2 text-right"><MoneyText :value="b.budget" /></td>
          <td class="px-3 py-2"><DeadlineBadge :deadline-at="b.deadline_at" /></td>
          <td class="px-3 py-2 text-text-2">
            {{ b.source === 'prespec' ? copy.bid.prespec : copy.bid.regular }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

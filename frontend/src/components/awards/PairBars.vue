<script setup lang="ts">
// 우리·상대 두 계열 막대 (§15.7 한눈에 보기·연도별). 범주 색은 고정 순서 --series-1(우리), --series-2(상대).
// 두 계열이라 범례를 두고 값도 막대 옆에 적는다(색만으로 구분하지 않음). null은 '수집 중'.
import { computed } from 'vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'
import type { PairRow } from './pair'

// scale: shared는 모든 줄이 같은 축(연도별), row는 줄마다 두 값끼리만(단위가 다른 지표들)
const props = withDefaults(
  defineProps<{ rows: PairRow[]; usName: string; themName: string; scale?: 'shared' | 'row' }>(),
  { scale: 'shared' },
)
const sharedMax = computed(() => Math.max(1, ...props.rows.flatMap((r) => [r.us ?? 0, r.them ?? 0])))
function width(r: PairRow, v: number | null): string {
  const max = props.scale === 'row' ? Math.max(1, r.us ?? 0, r.them ?? 0) : sharedMax.value
  return `${((v ?? 0) / max) * 100}%`
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <ul class="flex flex-wrap gap-4 text-xs text-text-2" data-legend>
      <li class="flex items-center gap-1.5">
        <span class="size-2.5 rounded-sm" :style="{ background: 'var(--series-1)' }" aria-hidden="true" />
        {{ copy.competitors.legendUs(usName) }}
      </li>
      <li class="flex items-center gap-1.5">
        <span class="size-2.5 rounded-sm" :style="{ background: 'var(--series-2)' }" aria-hidden="true" />
        {{ copy.competitors.legendThem(themName) }}
      </li>
    </ul>
    <ul class="flex flex-col gap-3">
      <li v-for="r in rows" :key="r.key" class="grid grid-cols-[7rem_1fr] items-center gap-3 text-sm" :data-pair="r.key">
        <span class="text-text-2">{{ r.label }}</span>
        <span v-if="r.collecting && r.us === null && r.them === null"><UiBadge tone="warning">{{ copy.awards.collecting }}</UiBadge></span>
        <span v-else class="flex flex-col gap-0.5">
          <span class="flex items-center gap-2" :title="`${copy.competitors.colUs} ${r.usText}`">
            <span class="h-2.5 rounded-r-[4px]" :style="{ width: width(r, r.us), background: 'var(--series-1)' }" />
            <span class="whitespace-nowrap text-xs tabular">{{ r.usText }}</span>
          </span>
          <span class="flex items-center gap-2" :title="`${copy.competitors.colThem} ${r.themText}`">
            <span class="h-2.5 rounded-r-[4px]" :style="{ width: width(r, r.them), background: 'var(--series-2)' }" />
            <span class="whitespace-nowrap text-xs tabular">{{ r.themText }}</span>
            <UiBadge v-if="r.collecting" tone="warning">{{ copy.awards.collecting }}</UiBadge>
          </span>
        </span>
      </li>
    </ul>
  </div>
</template>

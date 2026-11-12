<script setup lang="ts">
// 평가 배점 (요약·분석 공용). 한 줄 비율 막대로 기술·가격 몫을 보여 주고, 아래 항목별 막대와 점수를 둔다.
// 가격 항목(이름에 '가격')은 회색, 나머지는 기술(파랑). 색만으로 구분하지 않도록 범례에 이름과 점수를 쓴다.
import { computed } from 'vue'
import type { AnalysisResult } from '@/api/types'
import { copy } from '@/copy'

const props = defineProps<{ evaluation: AnalysisResult['evaluation'] }>()
const isPrice = (name: string) => name.includes(copy.analysis.match.price)
const scored = computed(() =>
  (props.evaluation.items ?? [])
    .filter((e) => e.points != null && e.points > 0)
    .map((e) => ({ ...e, points: e.points as number, kind: isPrice(e.name) ? 'price' : 'tech' })),
)
const total = computed(() => scored.value.reduce((a, e) => a + e.points, 0))
const max = computed(() => Math.max(1, ...scored.value.map((e) => e.points)))
const sum = (kind: string) => scored.value.filter((e) => e.kind === kind).reduce((a, e) => a + e.points, 0)
const pct = (n: number, of: number) => `${Math.round((n / of) * 1000) / 10}%`
</script>

<template>
  <div class="flex flex-col gap-3">
    <p v-if="evaluation.method" class="text-base text-text">{{ evaluation.method }}</p>
    <template v-if="scored.length">
      <div class="flex h-3 gap-0.5 overflow-hidden rounded-full" role="img" :aria-label="copy.analysis.scoreBar(sum('tech'), sum('price'))">
        <span
          v-for="(e, i) in scored"
          :key="i"
          :data-seg="e.kind"
          :class="e.kind === 'price' ? 'bg-text-3' : 'bg-primary'"
          :style="{ width: pct(e.points, total) }"
        />
      </div>
      <p class="flex flex-wrap gap-x-4 gap-y-1 text-sm text-text-2">
        <span class="inline-flex items-center gap-1.5">
          <span class="size-2.5 rounded-full bg-primary" aria-hidden="true" />{{ copy.analysis.techScore }} {{ copy.analysis.points(sum('tech')) }}
        </span>
        <span v-if="sum('price')" class="inline-flex items-center gap-1.5">
          <span class="size-2.5 rounded-full bg-text-3" aria-hidden="true" />{{ copy.analysis.priceScore }} {{ copy.analysis.points(sum('price')) }}
        </span>
      </p>
    </template>
    <ul v-if="evaluation.items?.length" class="flex flex-col gap-2">
      <li v-for="(e, i) in evaluation.items" :key="i" class="grid grid-cols-[minmax(0,1fr)_2.5rem_2.75rem] items-center gap-2 text-base sm:grid-cols-[minmax(0,1fr)_5rem_3rem] sm:gap-3">
        <span class="min-w-0">
          {{ e.name }}<span v-if="e.note" class="text-sm text-text-3"> ({{ e.note }})</span>
        </span>
        <span class="h-1.5 rounded-full bg-surface-2" aria-hidden="true">
          <span
            v-if="e.points"
            class="block h-full rounded-full"
            :class="isPrice(e.name) ? 'bg-text-3' : 'bg-primary'"
            :style="{ width: pct(e.points, max) }"
          />
        </span>
        <span class="tabular text-right text-text-2">{{ e.points != null ? copy.analysis.points(e.points) : '' }}</span>
      </li>
    </ul>
  </div>
</template>

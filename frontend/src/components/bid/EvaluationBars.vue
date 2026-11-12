<script setup lang="ts">
// 평가 배점 (요약·분석 공용, P7). 항목마다 고정 순서의 범주 색(--series-1..8)을 주고, 한 줄 누적 막대의 조각과
// 아래 목록의 견본·미니 막대가 같은 색을 쓴다. 9번째부터는 새 색을 만들지 않고 '기타'로 묶는다(dataviz 규칙).
// 색만으로 구분하지 않도록 목록에 이름·점수가 항상 있고, 기술·가격 합계는 글로 쓴다.
import { computed } from 'vue'
import type { AnalysisResult } from '@/api/types'
import { copy } from '@/copy'

const SLOTS = 8
const props = defineProps<{ evaluation: AnalysisResult['evaluation'] }>()

const isPrice = (name: string) => name.includes(copy.analysis.match.price)
const pct = (n: number, of: number) => `${Math.round((n / of) * 1000) / 10}%`
const color = (slot: string) => `var(--series-${slot})`

/** 배점 있는 항목에만 색 순번을 준다(목록 순서 = 색 순서, 순환 없음). */
const rows = computed(() => {
  let k = 0
  return (props.evaluation.items ?? []).map((e) => {
    const scored = e.points != null && e.points > 0
    const slot = scored ? (k < SLOTS ? String(++k) : (k++, 'other')) : null
    return { ...e, slot }
  })
})
const scored = computed(() => rows.value.filter((r) => r.slot !== null) as Array<(typeof rows.value)[number] & { slot: string; points: number }>)
const total = computed(() => scored.value.reduce((a, e) => a + e.points, 0))
const max = computed(() => Math.max(1, ...scored.value.map((e) => e.points)))
const segments = computed(() => {
  const own = scored.value.filter((e) => e.slot !== 'other').map((e) => ({ slot: e.slot, points: e.points, name: e.name }))
  const rest = scored.value.filter((e) => e.slot === 'other')
  if (rest.length) {
    own.push({ slot: 'other', points: rest.reduce((a, e) => a + e.points, 0), name: copy.analysis.otherItems(rest.length) })
  }
  return own
})
const sum = (price: boolean) => scored.value.filter((e) => isPrice(e.name) === price).reduce((a, e) => a + e.points, 0)
</script>

<template>
  <div class="flex flex-col gap-3">
    <p v-if="evaluation.method" class="text-base text-text">{{ evaluation.method }}</p>
    <template v-if="segments.length">
      <div
        class="flex h-3 gap-0.5 overflow-hidden rounded-[4px] bg-surface"
        role="img"
        :aria-label="copy.analysis.scoreBar(sum(false), sum(true))"
      >
        <span
          v-for="s in segments"
          :key="s.slot"
          :data-seg="s.slot"
          :title="`${s.name} ${copy.analysis.points(s.points)}`"
          :style="{ width: pct(s.points, total), backgroundColor: color(s.slot) }"
        />
      </div>
      <p class="flex flex-wrap gap-x-4 gap-y-1 text-sm text-text-2">
        <span>{{ copy.analysis.techScore }} {{ copy.analysis.points(sum(false)) }}</span>
        <span v-if="sum(true)">{{ copy.analysis.priceScore }} {{ copy.analysis.points(sum(true)) }}</span>
      </p>
    </template>
    <ul v-if="rows.length" class="flex flex-col gap-2">
      <li
        v-for="(e, i) in rows"
        :key="i"
        class="grid grid-cols-[0.625rem_minmax(0,1fr)_2.5rem_2.75rem] items-center gap-2 text-base sm:grid-cols-[0.625rem_minmax(0,1fr)_5rem_3rem] sm:gap-3"
      >
        <span
          v-if="e.slot"
          data-swatch
          class="size-2.5 rounded-[2px]"
          :style="{ backgroundColor: color(e.slot) }"
          aria-hidden="true"
        />
        <span v-else class="size-2.5 rounded-[2px] border border-border-input" aria-hidden="true" />
        <span class="min-w-0">
          {{ e.name }}<span v-if="e.note" class="text-sm text-text-3"> ({{ e.note }})</span>
        </span>
        <span class="h-1.5 rounded-[2px] bg-surface-2" aria-hidden="true">
          <span
            v-if="e.slot && e.points"
            class="block h-full rounded-[2px]"
            :style="{ width: pct(e.points, max), backgroundColor: color(e.slot) }"
          />
        </span>
        <span class="tabular text-right text-text-2">{{ e.points != null ? copy.analysis.points(e.points) : '' }}</span>
      </li>
    </ul>
  </div>
</template>

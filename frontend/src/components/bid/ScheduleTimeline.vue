<script setup lang="ts">
// 일정 (요약·분석 공용). 공고문 순서 그대로 세로 타임라인. 이름에 '마감'이 있으면 배지로 강조한다.
import type { AnalysisResult } from '@/api/types'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'

defineProps<{ items: AnalysisResult['schedule'] }>()
const isDeadline = (label: string) => label.includes(copy.analysis.match.deadline)
</script>

<template>
  <ol class="relative ml-1 flex flex-col gap-3 border-l-2 border-primary-soft pl-4">
    <li v-for="(s, i) in items" :key="i" class="relative flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5">
      <span
        class="absolute -left-[1.3125rem] top-1.5 size-2.5 rounded-full ring-2 ring-surface"
        :class="isDeadline(s.label) ? 'bg-warning-fg' : 'bg-primary'"
        aria-hidden="true"
      />
      <span class="flex items-center gap-2 text-base" :class="isDeadline(s.label) ? 'font-medium text-text' : 'text-text'">
        {{ s.label }}<UiBadge v-if="isDeadline(s.label)" tone="warning">{{ copy.analysis.deadline }}</UiBadge>
      </span>
      <span class="tabular text-sm text-text-2">{{ s.date || s.raw || '' }}</span>
    </li>
  </ol>
</template>

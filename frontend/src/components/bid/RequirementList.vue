<script setup lang="ts">
// 핵심 요구사항 (요약·분석 공용). 항목마다 종류 배지. detailed면 근거 발췌·파일명도 보여 준다(분석).
import type { AnalysisResult } from '@/api/types'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'

defineProps<{ items: AnalysisResult['requirements']; detailed?: boolean }>()
</script>

<template>
  <ul class="flex flex-col divide-y divide-border">
    <li v-for="(r, i) in items" :key="i" class="flex items-start gap-3 py-2 first:pt-0 last:pb-0">
      <UiBadge class="mt-0.5 w-14 shrink-0 justify-center" :tone="r.kind === 'other' ? 'neutral' : 'primary'">
        {{ copy.analysis.kind[r.kind ?? 'other'] }}
      </UiBadge>
      <span class="min-w-0 text-base">
        {{ r.text }}
        <template v-if="detailed">
          <span v-if="r.source" class="ml-1 text-sm text-text-3">{{ copy.analysis.source(r.source) }}</span>
          <q v-if="r.evidence" class="mt-1 block text-sm text-text-2">{{ r.evidence }}</q>
        </template>
      </span>
    </li>
  </ul>
</template>

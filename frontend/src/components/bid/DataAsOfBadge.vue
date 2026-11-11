<script setup lang="ts">
// 데이터 기준 배지 (SPEC §7.2). incomplete이면 경고 톤과 '일부 기간은 수집 중' 문구.
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'
import { formatDataAsOf } from '@/utils/format'

defineProps<{ asOf: string | null | undefined; incomplete?: boolean }>()
</script>

<template>
  <span class="inline-flex flex-wrap items-center gap-1.5">
    <UiBadge v-if="asOf" :tone="incomplete ? 'warning' : 'neutral'">
      {{ copy.data.asOf(formatDataAsOf(asOf)) }}
    </UiBadge>
    <UiBadge v-if="incomplete" tone="warning">{{ copy.data.incomplete }}</UiBadge>
  </span>
</template>

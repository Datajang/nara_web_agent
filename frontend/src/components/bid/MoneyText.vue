<script setup lang="ts">
// 금액 (SPEC §10.5): 억·만 단위로 줄이고 툴팁에 원 단위 전체.
import { copy } from '@/copy'
import { formatMoney } from '@/utils/format'

defineProps<{ value: number | null | undefined }>()
</script>

<template>
  <span class="tabular" :title="value ? `${value.toLocaleString('ko-KR')}${copy.format.won}` : undefined">
    {{ formatMoney(value) }}
  </span>
</template>

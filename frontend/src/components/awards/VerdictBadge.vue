<script setup lang="ts">
// 판정 배지 (§15.7): 색만으로 구분하지 않고 '▲ 앞섬'·'= 비슷'·'▼ 뒤처짐'·'참고' 글자를 함께 쓴다(§10.1).
import type { Verdict } from '@/api/competitors'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'

defineProps<{ verdict: Verdict; smallSample?: boolean }>()
const tone = { up: 'success', same: 'neutral', down: 'danger', info: 'primary' } as const
</script>

<template>
  <span class="inline-flex flex-wrap items-center gap-1" :data-verdict="verdict">
    <UiBadge :tone="tone[verdict]">{{ copy.competitors.verdicts[verdict] }}</UiBadge>
    <UiBadge v-if="smallSample" tone="warning">{{ copy.competitors.smallSample }}</UiBadge>
  </span>
</template>

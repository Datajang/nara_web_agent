<script setup lang="ts">
// 낙찰 화면 머리의 고정 문구 (§15.1 원칙 3, §15.7): '공개된 나라장터 낙찰 기준'과 실제로 센 기간.
// 수집이 끝나지 않았으면 'YYYY-MM-DD 이후 기준'을 적어 0건으로 오해하지 않게 한다.
import type { AwardPeriod } from '@/api/awards'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'

defineProps<{ period: AwardPeriod }>()
</script>

<template>
  <div class="flex flex-wrap items-center gap-2 text-sm text-text-2" data-awards-basis>
    <UiBadge tone="primary">{{ copy.awards.basis }}</UiBadge>
    <template v-if="period.counted_from && period.counted_to">
      <span class="tabular">{{ copy.awards.countedRange(period.counted_from, period.counted_to) }}</span>
      <UiBadge v-if="period.collecting" tone="warning">{{ copy.awards.collecting }}</UiBadge>
      <span v-if="period.collecting">{{ copy.awards.collectingFrom(period.counted_from) }}</span>
    </template>
    <template v-else>
      <UiBadge tone="warning">{{ copy.awards.collecting }}</UiBadge>
      <span>{{ copy.awards.nothingCollected }}</span>
    </template>
  </div>
</template>

<script setup lang="ts">
// 마감 공고 사유 배지(2026-11-26): 낙찰·유찰·개찰완료·재입찰·개찰 전·결과 대기·의견 마감.
// 서버가 DB(낙찰·개찰 상태)로 정한 outcome을 그대로 그린다. 진행 중이면 null이라 그리지 않는다.
// 업체 이름이 길면 말줄임, 전체 문구는 title로.
import { computed } from 'vue'
import type { BidOutcome } from '@/api/types'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'
import type { Tone } from '@/stores/ui'
import { formatShortDate } from '@/utils/format'

const props = defineProps<{ outcome: BidOutcome | null | undefined }>()
const t = copy.bid.outcome

const view = computed<{ label: string; tone: Tone } | null>(() => {
  const o = props.outcome
  if (!o) return null
  switch (o.kind) {
    case 'awarded':
      return { label: t.awarded(o.company ?? null, o.more ?? 0), tone: 'success' }
    case 'failed':
      return { label: t.failed(o.reason ?? null), tone: 'danger' }
    case 'opened':
      return { label: t.opened(o.company ?? null), tone: 'warning' }
    case 'rebid':
      return { label: t.rebid, tone: 'warning' }
    case 'before_opening':
      return { label: o.opening_at ? t.beforeOpening(formatShortDate(o.opening_at)) : t.waiting, tone: 'neutral' }
    case 'waiting':
      return { label: t.waiting, tone: 'neutral' }
    case 'prespec_closed':
      return { label: t.prespecClosed, tone: 'neutral' }
    default:
      return null
  }
})
</script>

<template>
  <UiBadge v-if="view" :tone="view.tone" class="max-w-64" :title="view.label" data-outcome>
    <span class="truncate">{{ view.label }}</span>
  </UiBadge>
</template>

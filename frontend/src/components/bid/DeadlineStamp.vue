<script setup lang="ts">
// 공고 대장 왼쪽 칸: 남은 날(D-n)을 크게, 마감 시각을 작게. 3일 이내는 관인 도장 모양으로 강조한다
// (브랜드 표식과 같은 주홍 테두리). 색만으로 전하지 않도록 'D-n' 글자가 항상 있다.
import { computed } from 'vue'
import { formatDateTime, formatDday, formatShortDate } from '@/utils/format'
import { deadlineTone } from './tones'

const props = defineProps<{ deadlineAt: string | null | undefined; now?: Date }>()
const now = computed(() => props.now ?? new Date())
const tone = computed(() => deadlineTone(props.deadlineAt, now.value))
const open = computed(() => !!props.deadlineAt && new Date(props.deadlineAt).getTime() > now.value.getTime())
const label = computed(() => formatDday(props.deadlineAt, now.value))
</script>

<template>
  <div class="flex flex-col items-start gap-1" :title="deadlineAt ? formatDateTime(deadlineAt) : undefined">
    <span
      v-if="open && tone === 'danger'"
      data-urgent
      class="inline-flex h-8 items-center rounded-tag border-2 border-danger-fg px-1.5 text-md font-semibold tabular leading-none text-danger-fg"
    >{{ label }}</span>
    <span
      v-else
      class="text-md font-semibold tabular leading-8"
      :class="open ? (tone === 'warning' ? 'text-warning-fg' : 'text-text') : 'text-sm font-medium text-text-3'"
    >{{ label }}</span>
    <span v-if="deadlineAt" class="text-xs tabular text-text-3">{{ formatShortDate(deadlineAt) }}</span>
  </div>
</template>

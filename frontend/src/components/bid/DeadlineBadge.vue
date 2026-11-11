<script setup lang="ts">
// 마감 배지 (SPEC §10.4): D-3, D-day, 마감, 마감 미정. 툴팁에 정확한 시각(KST).
import { computed } from 'vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import { formatDateTime, formatDday } from '@/utils/format'
import { deadlineTone } from './tones'

const props = defineProps<{ deadlineAt: string | null | undefined; now?: Date }>()
const now = computed(() => props.now ?? new Date())
const tone = computed(() => deadlineTone(props.deadlineAt, now.value))
</script>

<template>
  <UiBadge
    :tone="tone"
    :data-tone="tone"
    :title="deadlineAt ? formatDateTime(deadlineAt) : undefined"
  >
    {{ formatDday(deadlineAt, now) }}
  </UiBadge>
</template>

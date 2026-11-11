<script setup lang="ts">
// 적합도 점수 배지 (SPEC §10.4, §7.4): 숫자 + 라벨(높음·보통·낮음), 툴팁은 'AI 추정'.
import { computed } from 'vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'
import { scoreTone } from './tones'

const props = defineProps<{ score: number }>()
const tone = computed(() => scoreTone(props.score))
const label = computed(() =>
  props.score >= 80 ? copy.score.high : props.score >= 60 ? copy.score.mid : copy.score.low,
)
</script>

<template>
  <UiBadge :tone="tone" :data-tone="tone" :title="copy.score.tooltip">
    {{ copy.score.points(score) }} · {{ label }}
  </UiBadge>
</template>

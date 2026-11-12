<script setup lang="ts">
// 배지 (SPEC §10.4). 서식의 꼬리표처럼 각진 작은 표. 색만으로 의미를 전달하지 않도록 항상 텍스트를 담는다.
import type { Tone } from '@/stores/ui'

withDefaults(defineProps<{ tone?: Tone; size?: 'sm' | 'md' }>(), { tone: 'neutral', size: 'sm' })

const tones: Record<Tone, string> = {
  neutral: 'bg-neutral-bg text-neutral-fg',
  primary: 'bg-primary-soft text-primary-hover',
  success: 'bg-success-bg text-success-fg',
  warning: 'bg-warning-bg text-warning-fg',
  danger: 'bg-danger-bg text-danger-fg',
}
</script>

<template>
  <span
    class="inline-flex items-center whitespace-nowrap rounded-tag font-medium tabular"
    :class="[tones[tone], size === 'sm' ? 'h-5 px-1.5 text-xs' : 'h-6 px-2 text-sm']"
  >
    <slot />
  </span>
</template>

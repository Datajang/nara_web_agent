<script setup lang="ts">
// 로딩 자리표시 (SPEC §7.2). 스크린리더에는 '불러오는 중' 한 번만 알린다.
import { copy } from '@/copy'

withDefaults(defineProps<{ lines?: number }>(), { lines: 3 })
</script>

<template>
  <div role="status" class="flex flex-col gap-2">
    <span class="sr-only">{{ copy.common.loading }}</span>
    <div
      v-for="n in lines"
      :key="n"
      class="h-16 animate-pulse rounded-card bg-surface-2 motion-reduce:animate-none"
      aria-hidden="true"
    />
  </div>
</template>

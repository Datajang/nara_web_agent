<script setup lang="ts">
// 상단 바 56px: 페이지 제목. 768px 미만은 사이드바가 숨으므로 홈으로 가는 로고를 여기에 둔다.
import { RouterLink } from 'vue-router'
import { copy } from '@/copy'

defineProps<{ title: string }>()
</script>

<template>
  <header class="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-surface/95 px-4 backdrop-blur md:px-6">
    <RouterLink
      to="/"
      :aria-label="copy.app.home"
      class="inline-flex size-8 shrink-0 items-center justify-center rounded-control bg-primary text-sm font-semibold text-white md:hidden"
    >
      <span aria-hidden="true">N</span>
    </RouterLink>
    <h1 class="truncate text-xl font-semibold text-text">{{ title }}</h1>
    <div class="ml-auto flex items-center gap-2"><slot /></div>
  </header>
</template>

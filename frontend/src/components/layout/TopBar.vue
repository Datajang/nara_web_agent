<script setup lang="ts">
// 상단 바 56px: 페이지 제목. 768px 미만은 사이드바가 숨으므로 홈으로 가는 로고를 여기에 둔다.
import { RouterLink } from 'vue-router'
import { copy } from '@/copy'
import BrandMark from './BrandMark.vue'

defineProps<{ title: string }>()
</script>

<template>
  <header class="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-border bg-bg px-4 md:px-8">
    <RouterLink to="/" :aria-label="copy.app.home" class="md:hidden">
      <BrandMark size="sm" />
    </RouterLink>
    <h1 class="truncate text-xl font-semibold tracking-tight text-text md:text-2xl">{{ title }}</h1>
    <div class="ml-auto flex items-center gap-2"><slot /></div>
  </header>
</template>

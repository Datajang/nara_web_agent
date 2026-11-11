<script setup lang="ts">
// 상단 바 56px: 페이지 제목 (DataAsOfBadge는 P3).
defineProps<{ title: string }>()
</script>

<template>
  <header class="sticky top-0 z-20 flex h-14 items-center border-b border-border bg-surface/95 px-4 backdrop-blur md:px-6">
    <h1 class="truncate text-xl font-semibold text-text">{{ title }}</h1>
    <div class="ml-auto flex items-center gap-2"><slot /></div>
  </header>
</template>

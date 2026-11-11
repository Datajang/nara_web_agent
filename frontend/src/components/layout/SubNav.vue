<script setup lang="ts">
// 설정·관리자 화면 안의 하위 메뉴 (§7.1 경로를 링크로 잇는다).
import { RouterLink, useRoute } from 'vue-router'

defineProps<{ label: string; items: Array<{ to: string; label: string }> }>()
const route = useRoute()
</script>

<template>
  <nav :aria-label="label" class="flex gap-1 border-b border-border">
    <RouterLink
      v-for="i in items"
      :key="i.to"
      :to="i.to"
      class="-mb-px inline-flex h-10 items-center border-b-2 px-3 text-base font-medium"
      :class="route.path === i.to ? 'border-primary text-primary-hover' : 'border-transparent text-text-2 hover:text-text'"
      :aria-current="route.path === i.to ? 'page' : undefined"
    >{{ i.label }}</RouterLink>
  </nav>
</template>

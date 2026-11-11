<script setup lang="ts">
// 빈 상태 (SPEC §10.4): 이유 + 다음 행동 버튼 하나.
import { Inbox } from 'lucide-vue-next'

defineProps<{ title: string; description?: string }>()
</script>

<template>
  <div class="flex flex-col items-center gap-3 px-6 py-12 text-center">
    <Inbox class="size-8 text-text-3" aria-hidden="true" />
    <p class="text-lg font-semibold text-text">{{ title }}</p>
    <p v-if="description" class="max-w-md text-base text-text-2">{{ description }}</p>
    <div v-if="$slots.action" class="mt-2"><slot name="action" /></div>
  </div>
</template>

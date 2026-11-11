<script setup lang="ts">
// 403 화면 (SPEC §7.11-9). 관리자 경로에 일반 회원이 오면 주소를 유지한 채 보여 준다.
import { ShieldAlert } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { copy } from '@/copy'
</script>

<template>
  <div class="flex flex-col items-center gap-3 px-6 py-16 text-center">
    <ShieldAlert class="size-10 text-text-3" aria-hidden="true" />
    <h2 class="text-xl font-semibold text-text">{{ copy.page.forbiddenTitle }}</h2>
    <p class="max-w-md text-base text-text-2">{{ copy.page.forbiddenBody }}</p>
    <RouterLink to="/search" class="text-base font-medium text-primary-hover hover:underline">
      {{ copy.page.goHome }}
    </RouterLink>
  </div>
</template>

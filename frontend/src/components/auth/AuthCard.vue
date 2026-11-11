<script setup lang="ts">
// 인증 화면 공통 틀: 가운데 카드 하나 (SPEC §7.10).
import { copy } from '@/copy'

defineProps<{ title: string; subtitle?: string }>()
</script>

<template>
  <main id="main" class="flex min-h-screen items-start justify-center bg-bg px-4 py-12 sm:items-center">
    <div class="w-full max-w-sm">
      <p class="mb-6 text-center text-lg font-semibold text-primary-hover">{{ copy.app.name }}</p>
      <section class="rounded-card border border-border bg-surface p-6 shadow-card sm:p-8">
        <h1 class="text-2xl font-semibold text-text">{{ title }}</h1>
        <p v-if="subtitle" class="mt-2 text-base text-text-2">{{ subtitle }}</p>
        <div class="mt-6"><slot /></div>
      </section>
      <nav v-if="$slots.footer" class="mt-6 flex flex-col items-center gap-3 text-base">
        <slot name="footer" />
      </nav>
    </div>
  </main>
</template>

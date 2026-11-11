<script setup lang="ts">
import { useRouter } from 'vue-router'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { copy } from '@/copy'

const router = useRouter()
</script>

<template>
  <section class="rounded-card border border-border bg-surface">
    <EmptyState :title="copy.page.notFoundTitle" :description="copy.page.notFoundBody">
      <template #action>
        <UiButton variant="secondary" @click="router.push('/search')">{{ copy.page.goHome }}</UiButton>
      </template>
    </EmptyState>
  </section>
</template>

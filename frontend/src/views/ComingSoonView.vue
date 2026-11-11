<script setup lang="ts">
import EmptyState from '@/components/ui/EmptyState.vue'
import { copy } from '@/copy'
</script>

<template>
  <section class="rounded-card border border-border bg-surface">
    <EmptyState :title="copy.page.comingSoonTitle" :description="copy.page.comingSoonBody" />
  </section>
</template>

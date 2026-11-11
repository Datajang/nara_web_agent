<script setup lang="ts">
// 개발 전용 컴포넌트 목록 (SPEC §10.11-4). 디자인 톤을 먼저 확인하는 곳. 운영 빌드 라우트에 없다.
import { ref } from 'vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiModal from '@/components/ui/UiModal.vue'
import { copy } from '@/copy'
import { useUiStore } from '@/stores/ui'
import { formatMoney } from '@/utils/format'

const ui = useUiStore()
const text = ref('')
const open = ref(false)
const money = [8500, 45000000, 120000000, 1500000000, null]
</script>

<template>
  <div class="flex flex-col gap-6">
    <section class="rounded-card border border-border bg-surface p-4">
      <h2 class="mb-3 text-lg font-semibold">{{ copy.dev.buttons }}</h2>
      <div class="flex flex-wrap gap-2">
        <UiButton>{{ copy.dev.primary }}</UiButton>
        <UiButton variant="secondary">{{ copy.dev.secondary }}</UiButton>
        <UiButton variant="ghost">{{ copy.dev.ghost }}</UiButton>
        <UiButton variant="danger">{{ copy.dev.danger }}</UiButton>
        <UiButton loading>{{ copy.dev.loading }}</UiButton>
        <UiButton size="sm" variant="secondary">{{ copy.dev.secondary }}</UiButton>
      </div>
    </section>
    <section class="rounded-card border border-border bg-surface p-4">
      <h2 class="mb-3 text-lg font-semibold">{{ copy.dev.inputs }}</h2>
      <div class="grid gap-4 md:grid-cols-2">
        <UiInput v-model="text" :label="copy.dev.sampleLabel" :hint="copy.dev.sampleHint" />
        <UiInput v-model="text" :label="copy.dev.sampleLabel" :error="copy.dev.sampleError" />
      </div>
    </section>
    <section class="rounded-card border border-border bg-surface p-4">
      <h2 class="mb-3 text-lg font-semibold">{{ copy.dev.badges }}</h2>
      <div class="flex flex-wrap items-center gap-2">
        <UiBadge>{{ copy.dev.badgeNeutral }}</UiBadge>
        <UiBadge tone="primary">{{ copy.dev.badgePrimary }}</UiBadge>
        <UiBadge tone="success">{{ copy.dev.badgeSuccess }}</UiBadge>
        <UiBadge tone="warning">{{ copy.dev.badgeWarning }}</UiBadge>
        <UiBadge tone="danger" size="md">{{ copy.dev.badgeDanger }}</UiBadge>
      </div>
      <h3 class="mb-2 mt-4 text-base font-medium">{{ copy.dev.money }}</h3>
      <p class="flex flex-wrap gap-4 text-sm tabular text-text-2">
        <span v-for="m in money" :key="String(m)">{{ formatMoney(m) }}</span>
      </p>
    </section>
    <section class="rounded-card border border-border bg-surface p-4">
      <h2 class="mb-3 text-lg font-semibold">{{ copy.dev.feedback }}</h2>
      <div class="flex flex-wrap gap-2">
        <UiButton variant="secondary" @click="open = true">{{ copy.dev.openModal }}</UiButton>
        <UiButton variant="secondary" @click="ui.toast(copy.dev.toastMessage, 'success')">
          {{ copy.dev.showToast }}
        </UiButton>
      </div>
      <UiModal v-model:open="open" :title="copy.dev.openModal" :description="copy.dev.modalBody">
        <template #actions>
          <UiButton @click="open = false">{{ copy.common.confirm }}</UiButton>
        </template>
      </UiModal>
    </section>
    <section class="rounded-card border border-border bg-surface">
      <h2 class="px-4 pt-4 text-lg font-semibold">{{ copy.dev.empty }}</h2>
      <EmptyState :title="copy.page.comingSoonTitle" :description="copy.search.empty">
        <template #action><UiButton variant="secondary">{{ copy.common.retry }}</UiButton></template>
      </EmptyState>
    </section>
  </div>
</template>

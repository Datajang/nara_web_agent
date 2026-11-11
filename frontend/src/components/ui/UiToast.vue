<script setup lang="ts">
// 토스트 영역 (SPEC §10.4). aria-live=polite, 오류는 수동으로 닫는다.
import { X } from 'lucide-vue-next'
import { copy } from '@/copy'
import { useUiStore, type Tone } from '@/stores/ui'

const ui = useUiStore()
const tones: Record<Tone, string> = {
  neutral: 'border-border',
  primary: 'border-primary',
  success: 'border-success-fg',
  warning: 'border-warning-fg',
  danger: 'border-danger-fg',
}
</script>

<template>
  <div
    aria-live="polite"
    class="pointer-events-none fixed inset-x-4 bottom-20 z-50 flex flex-col items-center gap-2 md:bottom-6"
  >
    <div
      v-for="t in ui.toasts"
      :key="t.id"
      :role="t.tone === 'danger' ? 'alert' : 'status'"
      class="pointer-events-auto flex w-full max-w-md items-start gap-3 rounded-card border-l-4 bg-surface px-4 py-3 text-base text-text shadow-pop"
      :class="tones[t.tone]"
    >
      <p class="flex-1">{{ t.message }}</p>
      <button
        type="button"
        class="-m-2 inline-flex size-10 items-center justify-center rounded-control text-text-3 hover:bg-surface-2"
        :aria-label="copy.common.close"
        @click="ui.dismiss(t.id)"
      >
        <X class="size-4" aria-hidden="true" />
      </button>
    </div>
  </div>
</template>

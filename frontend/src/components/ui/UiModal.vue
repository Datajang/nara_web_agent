<script setup lang="ts">
// 모달 (SPEC §10.4). Reka Dialog: 포커스 트랩, Esc로 닫기, 닫으면 연 요소로 포커스 복귀.
import {
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
} from 'reka-ui'
import { X } from 'lucide-vue-next'
import { copy } from '@/copy'

defineProps<{ title: string; description?: string }>()
const open = defineModel<boolean>('open', { default: false })
</script>

<template>
  <DialogRoot v-model:open="open">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-40 bg-text/40" />
      <DialogContent
        class="fixed left-1/2 top-1/2 z-50 w-[calc(100vw-32px)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-card bg-surface p-6 shadow-pop"
      >
        <div class="mb-4 flex items-start justify-between gap-4">
          <DialogTitle class="text-lg font-semibold text-text">{{ title }}</DialogTitle>
          <DialogClose
            class="-m-2 inline-flex size-10 items-center justify-center rounded-control text-text-3 hover:bg-surface-2"
            :aria-label="copy.common.close"
          >
            <X class="size-4" aria-hidden="true" />
          </DialogClose>
        </div>
        <DialogDescription v-if="description" class="mb-6 text-base text-text-2">
          {{ description }}
        </DialogDescription>
        <slot />
        <div v-if="$slots.actions" class="mt-6 flex justify-end gap-2">
          <slot name="actions" />
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

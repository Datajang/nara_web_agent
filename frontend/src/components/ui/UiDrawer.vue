<script setup lang="ts">
// 드로어 (SPEC §10.4). 모달과 같은 접근성 규칙(포커스 트랩, Esc, 포커스 복귀), 오른쪽에서 열린다.
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
        class="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col bg-surface shadow-pop"
      >
        <div class="flex items-start justify-between gap-4 border-b border-border p-4">
          <DialogTitle class="text-lg font-semibold text-text">{{ title }}</DialogTitle>
          <DialogClose
            class="-m-2 inline-flex size-10 items-center justify-center rounded-control text-text-3 hover:bg-surface-2"
            :aria-label="copy.common.close"
          >
            <X class="size-4" aria-hidden="true" />
          </DialogClose>
        </div>
        <DialogDescription v-if="description" class="px-4 pt-3 text-sm text-text-2">
          {{ description }}
        </DialogDescription>
        <div class="min-h-0 flex-1 overflow-y-auto p-4"><slot /></div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<script setup lang="ts">
// 첨부 목록 (SPEC §7.5-2): 이름·구분·상태 배지. 읽은 파일은 본문 미리보기 드로어를 연다.
import { FileText } from 'lucide-vue-next'
import type { BidDetail } from '@/api/types'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'

type File = BidDetail['files'][number]
defineProps<{ files: File[] }>()
const emit = defineEmits<{ preview: [File] }>()
const tone = { new: 'neutral', ok: 'success', failed: 'danger', unsupported: 'warning' } as const
</script>

<template>
  <p v-if="!files.length" class="text-text-3">{{ copy.detail.noFiles }}</p>
  <ul v-else class="divide-y divide-border rounded-card border border-border bg-surface">
    <li v-for="f in files" :key="f.file_id" class="flex flex-wrap items-center gap-2 px-4 py-3">
      <FileText class="size-4 text-text-3" aria-hidden="true" />
      <button
        v-if="f.status === 'ok'"
        type="button"
        class="min-h-10 text-left text-base text-primary-hover hover:underline"
        :aria-label="copy.detail.previewOpen(f.name)"
        @click="emit('preview', f)"
      >
        {{ f.name }}
      </button>
      <span v-else class="text-base text-text">{{ f.name }}</span>
      <span class="text-sm text-text-3">{{ copy.detail.fileKind[f.kind] }}</span>
      <UiBadge :tone="tone[f.status]" class="ml-auto">{{ copy.detail.fileStatus[f.status] }}</UiBadge>
    </li>
  </ul>
</template>

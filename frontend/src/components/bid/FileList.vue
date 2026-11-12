<script setup lang="ts">
// 첨부 목록 (SPEC §7.5-2): 이름을 누르면 원본을 내려받고, 읽은 파일은 눈 아이콘으로 본문(AI가 읽은 글자)을 본다.
import { Download, Eye, FileText, LoaderCircle } from 'lucide-vue-next'
import type { BidDetail } from '@/api/types'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'

type File = BidDetail['files'][number]
defineProps<{ files: File[]; downloading?: number | null }>()
const emit = defineEmits<{ preview: [File]; download: [File] }>()
const tone = { new: 'neutral', ok: 'success', failed: 'danger', unsupported: 'warning' } as const
</script>

<template>
  <p v-if="!files.length" class="text-text-3">{{ copy.detail.noFiles }}</p>
  <ul v-else class="divide-y divide-border rounded-card border border-border bg-surface">
    <li v-for="f in files" :key="f.file_id" class="flex items-start gap-3 px-4 py-2.5">
      <FileText class="mt-2.5 size-4 shrink-0 text-text-3" aria-hidden="true" />
      <div class="flex min-w-0 flex-1 flex-col">
        <button
          type="button"
          class="group inline-flex min-h-10 items-center gap-1.5 text-left text-base text-primary hover:underline disabled:opacity-60"
          :aria-label="copy.detail.download(f.name)"
          :disabled="downloading === f.file_id"
          @click="emit('download', f)"
        >
          <span class="min-w-0 break-all">{{ f.name }}</span>
          <LoaderCircle v-if="downloading === f.file_id" class="size-4 shrink-0 animate-spin" aria-hidden="true" />
          <Download v-else class="size-4 shrink-0 opacity-60 group-hover:opacity-100" aria-hidden="true" />
          <span v-if="downloading === f.file_id" class="text-sm text-text-3">{{ copy.detail.downloading }}</span>
        </button>
        <span class="-mt-1.5 text-sm text-text-3">{{ copy.detail.fileKind[f.kind] }}</span>
      </div>
      <span class="flex shrink-0 items-center gap-1 pt-1">
        <button
          v-if="f.status === 'ok'"
          type="button"
          class="inline-flex size-9 items-center justify-center rounded-control text-text-2 hover:bg-surface-2 hover:text-text"
          :aria-label="copy.detail.previewOpen(f.name)"
          :title="copy.detail.previewOpen(f.name)"
          @click="emit('preview', f)"
        >
          <Eye class="size-4" aria-hidden="true" />
        </button>
        <UiBadge :tone="tone[f.status]">{{ copy.detail.fileStatus[f.status] }}</UiBadge>
      </span>
    </li>
  </ul>
</template>

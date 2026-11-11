<script setup lang="ts">
// 마크다운 렌더 (SPEC §7.2, §10.4). marked로 변환한 뒤 DOMPurify로 정제한다. v-html은 이 파일만 허용.
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { computed } from 'vue'

const props = defineProps<{ source: string }>()

DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

const html = computed(() =>
  DOMPurify.sanitize(marked.parse(props.source, { async: false, gfm: true }) as string, {
    FORBID_TAGS: ['style', 'iframe', 'form', 'input', 'img'],
  }),
)
</script>

<template>
  <div class="markdown text-base leading-relaxed text-text" v-html="html" />
</template>

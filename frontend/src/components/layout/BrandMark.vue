<script setup lang="ts">
// 브랜드 표식: 관인(도장)처럼 주홍 테두리 안의 '입찰'. 장식이 아니라 '공문·입찰'을 뜻하는 이 서비스의 한 가지 상징.
// 같은 도장 모양을 마감 임박(3일 이내) 표시에만 다시 쓴다(DeadlineStamp).
import { copy } from '@/copy'

withDefaults(defineProps<{ size?: 'sm' | 'md' }>(), { size: 'md' })
</script>

<template>
  <span
    class="inline-flex shrink-0 select-none items-center justify-center rounded-tag border-2 border-danger-fg bg-surface font-semibold leading-none tracking-tight text-danger-fg"
    :class="size === 'sm' ? 'size-7 text-[11px]' : 'size-8 text-xs'"
    aria-hidden="true"
  >{{ copy.app.seal }}</span>
</template>

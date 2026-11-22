<script setup lang="ts">
// 북마크 표시 (2026-11-22): 켜지면 관인 주홍(danger-fg)으로 꽉 채우고, 꺼지면 테두리만.
// 크기(size-*)는 부르는 쪽 class로 준다. 상태는 버튼의 aria-pressed가 알린다.
import { Bookmark } from 'lucide-vue-next'

defineProps<{ on: boolean }>()
</script>

<template>
  <Bookmark :class="on ? 'fill-danger-fg text-danger-fg' : ''" aria-hidden="true" />
</template>

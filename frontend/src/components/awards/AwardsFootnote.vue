<script setup lang="ts">
// 낙찰 화면 바닥의 고정 문구 (§15.9): 공개 정보의 사내 참고용 집계.
import { copy } from '@/copy'
</script>

<template>
  <p class="border-t border-border pt-3 text-sm text-text-3" data-awards-footnote>
    {{ copy.awards.internalOnly }}
  </p>
</template>

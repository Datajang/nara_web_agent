<script setup lang="ts">
// 한 줄 조건 막대 (2026-11-18 넓은 화면 개편, 시안 D). 목록 화면 위에 흰 카드 하나로
// 검색칸·전환·꼬리표를 한 줄에 두고, 좁아지면 줄을 바꾼다. #end는 넓을 때 오른쪽 끝으로 민다.
defineProps<{ label: string }>()
</script>

<template>
  <section
    :aria-label="label"
    class="flex flex-wrap items-center gap-x-3 gap-y-2.5 rounded-card border border-border bg-surface px-3.5 py-3"
  >
    <slot />
    <div v-if="$slots.end" data-filter-end class="flex flex-wrap items-center gap-2 lg:ml-auto">
      <slot name="end" />
    </div>
  </section>
</template>

<script setup lang="ts" generic="T extends string | number | null">
// 선택 상자. 네이티브 select라 키보드·스크린리더 동작이 기본으로 맞다.
import { useId } from 'vue'

defineProps<{ label: string; options: Array<{ value: T; label: string }>; hideLabel?: boolean }>()
const model = defineModel<T>({ required: true })
const id = useId()
</script>

<template>
  <div class="flex flex-col gap-1.5">
    <label v-if="!hideLabel" :for="id" class="text-base font-medium text-text">{{ label }}</label>
    <select
      :id="id"
      v-model="model"
      :aria-label="hideLabel ? label : undefined"
      class="h-10 rounded-control border border-border-input bg-surface px-3 text-base text-text"
    >
      <option v-for="o in options" :key="String(o.value)" :value="o.value">{{ o.label }}</option>
    </select>
  </div>
</template>

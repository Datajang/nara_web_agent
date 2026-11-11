<script setup lang="ts" generic="T extends string | number">
// 세그먼트 선택 (SPEC §10.4). 네이티브 라디오 묶음이라 화살표 키 이동이 기본으로 된다.
import { useId } from 'vue'

defineProps<{ label: string; options: Array<{ value: T; label: string }>; hideLabel?: boolean }>()
const model = defineModel<T>({ required: true })
const name = useId()
</script>

<template>
  <fieldset class="flex flex-col gap-1.5">
    <legend class="mb-1.5 text-base font-medium text-text" :class="hideLabel ? 'sr-only' : ''">
      {{ label }}
    </legend>
    <div class="inline-flex flex-wrap gap-1 rounded-control bg-surface-2 p-1">
      <label
        v-for="o in options"
        :key="String(o.value)"
        class="relative inline-flex h-8 cursor-pointer items-center rounded-[4px] px-3 text-sm font-medium text-text-2 has-[:checked]:bg-surface has-[:checked]:text-text has-[:checked]:shadow-card has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-primary"
      >
        <input v-model="model" class="sr-only" type="radio" :name="name" :value="o.value" />
        {{ o.label }}
      </label>
    </div>
  </fieldset>
</template>

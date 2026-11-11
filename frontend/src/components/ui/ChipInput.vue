<script setup lang="ts">
// 칩 입력 (SPEC §10.4). Enter·쉼표로 추가, 빈 입력에서 Backspace는 마지막 칩 삭제, 공백·중복 제거.
import { X } from 'lucide-vue-next'
import { ref, useId } from 'vue'
import { copy } from '@/copy'

const props = withDefaults(
  defineProps<{ label: string; hint?: string; max?: number; maxLength?: number }>(),
  { hint: '', max: 10, maxLength: 50 },
)
const model = defineModel<string[]>({ default: () => [] })
const draft = ref('')
const id = useId()

function add(): boolean {
  const v = draft.value.trim().slice(0, props.maxLength)
  draft.value = ''
  if (!v || model.value.includes(v) || model.value.length >= props.max) return false
  model.value = [...model.value, v]
  return true
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' || e.key === ',') {
    if (e.key === ',' || draft.value.trim()) e.preventDefault() // 빈 Enter는 폼 제출
    add()
  } else if (e.key === 'Backspace' && !draft.value && model.value.length) {
    model.value = model.value.slice(0, -1)
  }
}

function remove(chip: string) {
  model.value = model.value.filter((c) => c !== chip)
}

/** 폼 제출 직전에 입력 중인 글자도 칩으로 넣는다. */
defineExpose({ commit: add })
</script>

<template>
  <div class="flex flex-col gap-1.5">
    <label :for="id" class="text-base font-medium text-text">{{ label }}</label>
    <div
      class="flex min-h-10 flex-wrap items-center gap-1.5 rounded-control border border-border-input bg-surface px-2 py-1.5 focus-within:outline-2 focus-within:outline-primary"
    >
      <span
        v-for="chip in model"
        :key="chip"
        class="inline-flex h-7 items-center gap-1 rounded-full bg-primary-soft pl-2.5 pr-1 text-sm text-primary-hover"
      >
        {{ chip }}
        <button
          type="button"
          class="inline-flex size-6 items-center justify-center rounded-full hover:bg-surface"
          :aria-label="`${chip} ${copy.common.remove}`"
          @click="remove(chip)"
        >
          <X class="size-3.5" aria-hidden="true" />
        </button>
      </span>
      <input
        :id="id"
        v-model="draft"
        type="text"
        :maxlength="maxLength"
        :aria-describedby="hint ? `${id}-hint` : undefined"
        class="h-7 min-w-24 flex-1 bg-transparent px-1 text-base text-text outline-none"
        @keydown="onKey"
        @blur="add"
      />
    </div>
    <p v-if="hint" :id="`${id}-hint`" class="text-sm text-text-3">{{ hint }}</p>
  </div>
</template>

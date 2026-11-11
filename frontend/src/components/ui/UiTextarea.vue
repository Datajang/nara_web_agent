<script setup lang="ts">
// 여러 줄 입력 (SPEC §10.4). 라벨은 항상 보이고, 글자 수를 함께 보여 준다.
import { computed, useId } from 'vue'
import { copy } from '@/copy'

const props = withDefaults(
  defineProps<{
    label: string
    hint?: string
    error?: string
    maxLength?: number
    rows?: number
    placeholder?: string
    hideLabel?: boolean
  }>(),
  { hint: '', error: '', maxLength: undefined, rows: 4, placeholder: '', hideLabel: false },
)
const model = defineModel<string>({ default: '' })
const emit = defineEmits<{ keydown: [KeyboardEvent] }>()

const id = useId()
const hintId = `${id}-hint`
const errorId = `${id}-error`
const counterId = `${id}-count`
const describedBy = computed(
  () =>
    [props.hint ? hintId : '', props.error ? errorId : '', props.maxLength ? counterId : '']
      .filter(Boolean)
      .join(' ') || undefined,
)
</script>

<template>
  <div class="flex flex-col gap-1.5">
    <label :for="id" class="text-base font-medium text-text" :class="hideLabel ? 'sr-only' : ''">
      {{ label }}
    </label>
    <textarea
      :id="id"
      v-model="model"
      :rows="rows"
      :maxlength="maxLength"
      :placeholder="placeholder"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="describedBy"
      class="min-h-10 resize-y rounded-control border bg-surface px-3 py-2 text-base text-text placeholder:text-text-3"
      :class="error ? 'border-danger-fg' : 'border-border-input'"
      @keydown="emit('keydown', $event)"
    />
    <div class="flex justify-between gap-2 text-sm">
      <p v-if="hint" :id="hintId" class="text-text-3">{{ hint }}</p>
      <p v-if="error" :id="errorId" class="text-danger-fg">{{ error }}</p>
      <p v-if="maxLength" :id="counterId" class="ml-auto tabular text-text-3">
        {{ copy.common.chars(model.length, maxLength) }}
      </p>
    </div>
  </div>
</template>

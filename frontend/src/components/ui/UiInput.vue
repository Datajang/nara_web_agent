<script setup lang="ts">
// 입력 (SPEC §10.4). 라벨은 항상 보이고, 도움말·오류는 aria-describedby로 연결한다.
import { computed, useId } from 'vue'

const props = withDefaults(
  defineProps<{
    label: string
    type?: string
    hint?: string
    error?: string
    autocomplete?: string
    required?: boolean
    maxLength?: number
    name?: string
    placeholder?: string
    size?: 'md' | 'lg'
  }>(),
  {
    type: 'text',
    hint: '',
    error: '',
    autocomplete: 'off',
    required: false,
    maxLength: undefined,
    name: undefined,
    placeholder: undefined,
    size: 'md',
  },
)
const model = defineModel<string>({ default: '' })

const id = useId()
const hintId = `${id}-hint`
const errorId = `${id}-error`
const describedBy = computed(
  () => [props.hint ? hintId : '', props.error ? errorId : ''].filter(Boolean).join(' ') || undefined,
)
</script>

<template>
  <div class="flex flex-col gap-1.5">
    <label :for="id" class="text-base text-text" :class="size === 'lg' ? 'font-semibold' : 'font-medium'">{{
      label
    }}</label>
    <input
      :id="id"
      v-model="model"
      :type="type"
      :name="name"
      :autocomplete="autocomplete"
      :required="required"
      :maxlength="maxLength"
      :placeholder="placeholder"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="describedBy"
      class="rounded-control border bg-surface text-text placeholder:text-text-3"
      :class="[
        error ? 'border-danger-fg' : 'border-border-input',
        size === 'lg' ? 'h-12 px-3.5 text-md' : 'h-10 px-3 text-base',
      ]"
    />
    <p v-if="hint" :id="hintId" class="text-sm text-text-3">{{ hint }}</p>
    <p v-if="error" :id="errorId" class="text-sm text-danger-fg">{{ error }}</p>
  </div>
</template>

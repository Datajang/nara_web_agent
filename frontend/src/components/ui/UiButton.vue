<script setup lang="ts">
// 버튼 (SPEC §10.4). loading이면 폭을 유지한 채 스피너를 보이고 클릭을 막는다.
import { LoaderCircle } from 'lucide-vue-next'
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
    size?: 'sm' | 'md'
    type?: 'button' | 'submit'
    loading?: boolean
    disabled?: boolean
    block?: boolean
  }>(),
  { variant: 'primary', size: 'md', type: 'button', loading: false, disabled: false, block: false },
)

const classes = computed(() => [
  'relative inline-flex items-center justify-center gap-2 rounded-control font-medium',
  'transition-colors duration-150 ease-out disabled:cursor-not-allowed disabled:opacity-60',
  props.size === 'sm' ? 'h-8 px-3 text-sm' : 'h-10 px-4 text-base',
  props.block ? 'w-full' : '',
  {
    primary: 'bg-primary text-white hover:bg-primary-hover',
    secondary: 'border border-border-input bg-surface text-text hover:bg-surface-2',
    ghost: 'text-text-2 hover:bg-surface-2 hover:text-text',
    danger: 'bg-danger-fg text-white hover:opacity-90',
  }[props.variant],
])
</script>

<template>
  <button
    :type="type"
    :class="classes"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
  >
    <span :class="loading ? 'invisible' : 'inline-flex items-center gap-2'"><slot /></span>
    <LoaderCircle
      v-if="loading"
      class="absolute size-4 animate-spin"
      aria-hidden="true"
    />
  </button>
</template>

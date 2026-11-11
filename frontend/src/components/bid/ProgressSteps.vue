<script setup lang="ts">
// SSE 단계 표시 (SPEC §6.4, §10.4). 캐시 적중 단계는 '저장된 결과 사용'.
import { Check, LoaderCircle } from 'lucide-vue-next'
import type { Stage } from '@/api/types'
import { copy } from '@/copy'

const props = defineProps<{ stages: Stage[]; current: string | null; cached?: string[] }>()

function state(s: Stage): 'done' | 'current' | 'todo' {
  const i = props.stages.indexOf(s)
  const c = props.current ? props.stages.indexOf(props.current as Stage) : -1
  if (i < c) return 'done'
  return i === c ? 'current' : 'todo'
}
</script>

<template>
  <div aria-live="polite">
    <ol :aria-label="copy.stage.label" class="flex flex-wrap gap-x-4 gap-y-2">
      <li
        v-for="s in stages"
        :key="s"
        class="inline-flex items-center gap-1.5 text-sm"
        :class="state(s) === 'todo' ? 'text-text-3' : 'text-text'"
        :aria-current="state(s) === 'current' ? 'step' : undefined"
      >
        <Check v-if="state(s) === 'done'" class="size-4 text-success-fg" aria-hidden="true" />
        <LoaderCircle
          v-else-if="state(s) === 'current'"
          class="size-4 animate-spin text-primary motion-reduce:animate-none"
          aria-hidden="true"
        />
        <span v-else class="size-4 rounded-full border border-border-input" aria-hidden="true" />
        {{ copy.stage[s] }}
        <span v-if="cached?.includes(s)" class="text-text-3">({{ copy.stage.cached }})</span>
      </li>
    </ol>
  </div>
</template>

<script setup lang="ts">
// 분석 진행 로딩바 (SPEC §7.5-4). status 이벤트를 받은 시각으로 도장 찍고 1초마다 다시 계산한다.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { StreamEvent } from '@/api/types'
import { copy } from '@/copy'
import { formatDuration, progressState, type Stamped } from './progress'

const props = defineProps<{ events: StreamEvent[] }>()

const startedAt = Date.now()
const now = ref(startedAt)
const stamped = ref<Stamped[]>([])
let seen = 0

watch(
  () => props.events.length,
  (n) => {
    for (const e of props.events.slice(seen, n)) {
      if (e.type !== 'status') continue
      stamped.value.push({
        stage: e.stage,
        progress: e.progress,
        expected_s: e.expected_s,
        waiting: e.waiting,
        at: Date.now(),
      })
    }
    seen = n
  },
  { immediate: true },
)

const timer = setInterval(() => (now.value = Date.now()), 1000)
onBeforeUnmount(() => clearInterval(timer))

// 막대는 뒤로 가지 않는다(기다리는 동안 천천히 채운 뒤 실제 진행률이 더 낮게 올 때)
let shown = 0
const state = computed(() => {
  const s = progressState(stamped.value, startedAt, now.value)
  shown = Math.max(shown, s.percent)
  return { ...s, percent: shown }
})
const waiting = computed(() => stamped.value[stamped.value.length - 1]?.waiting === true)
const remainingText = computed(() => {
  if (waiting.value) return copy.progress.waiting
  const r = state.value.remainingS
  if (r === null) return ''
  return r <= 0 ? copy.progress.almostDone : copy.progress.remaining(r)
})
</script>

<template>
  <div class="flex flex-col gap-1.5">
    <div
      role="progressbar"
      :aria-label="copy.progress.label"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-valuenow="state.percent"
      class="h-2 w-full overflow-hidden rounded-full bg-surface-2"
    >
      <div
        class="h-full rounded-full bg-primary transition-[width] duration-700 ease-out motion-reduce:transition-none"
        :style="{ width: `${state.percent}%` }"
      />
    </div>
    <p class="flex justify-between text-sm text-text-3">
      <span>{{ copy.progress.elapsed(formatDuration(state.elapsedS)) }}</span>
      <span v-if="remainingText">{{ remainingText }}</span>
    </p>
  </div>
</template>

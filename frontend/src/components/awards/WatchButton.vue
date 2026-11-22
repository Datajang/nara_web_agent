<script setup lang="ts">
// 관심 경쟁사 추가·빼기 (§15.6 PUT·DELETE /competitors/watch). 서비스 전체가 함께 쓰는 목록이다.
// 누르자마자 별을 바꾸고(낙관적 갱신) 저장은 뒤에서 한다. 실패하면 되돌린다 (2026-11-22).
// 무거운 레이더(후보 목록)는 다시 부르지 않고, 화면에 있는 목록의 watched만 고친다.
import { useQueryClient } from '@tanstack/vue-query'
import { Star } from 'lucide-vue-next'
import { ref, watch } from 'vue'
import { competitorsApi, type CandidateList } from '@/api/competitors'
import UiButton from '@/components/ui/UiButton.vue'
import { copy } from '@/copy'
import { useUiStore } from '@/stores/ui'
import { generalMessage } from '@/utils/authErrors'

const props = defineProps<{ bizno: string; watched: boolean; size?: 'sm' | 'md' }>()
const emit = defineEmits<{ changed: [boolean] }>()
const ui = useUiStore()
const queryClient = useQueryClient()
const on = ref(props.watched)
let busy = false
watch(
  () => props.watched,
  (v) => {
    if (!busy) on.value = v
  },
)

function patchCandidates(next: boolean) {
  queryClient.setQueriesData<CandidateList>({ queryKey: ['competitors', 'candidates'] }, (old) =>
    old
      ? { ...old, items: old.items.map((c) => (c.bizno === props.bizno ? { ...c, watched: next } : c)) }
      : old,
  )
}

async function toggle() {
  if (busy) return
  busy = true
  const next = !on.value
  on.value = next
  try {
    if (next) await competitorsApi.watch(props.bizno)
    else await competitorsApi.unwatch(props.bizno)
    patchCandidates(next)
    emit('changed', next)
    ui.toast(next ? copy.competitors.watchAdded : copy.competitors.watchRemoved, 'success')
    void queryClient.invalidateQueries({ queryKey: ['competitors', 'watch'] })
  } catch (e) {
    on.value = !next
    ui.toast(generalMessage(e), 'danger')
  } finally {
    busy = false
  }
}
</script>

<template>
  <UiButton
    :size="size ?? 'sm'"
    variant="secondary"
    :aria-pressed="on"
    :aria-label="on ? copy.competitors.watchRemove : copy.competitors.watchAdd"
    data-watch
    @click="toggle"
  >
    <Star class="size-4" :class="on ? 'fill-current text-warning-fg' : ''" aria-hidden="true" />
    <span>{{ on ? copy.competitors.watchRemove : copy.competitors.watchAdd }}</span>
  </UiButton>
</template>

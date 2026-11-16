<script setup lang="ts">
// 관심 경쟁사 추가·빼기 (§15.6 PUT·DELETE /competitors/watch). 서비스 전체가 함께 쓰는 목록이다.
import { useQueryClient } from '@tanstack/vue-query'
import { Star } from 'lucide-vue-next'
import { ref } from 'vue'
import { competitorsApi } from '@/api/competitors'
import UiButton from '@/components/ui/UiButton.vue'
import { copy } from '@/copy'
import { useUiStore } from '@/stores/ui'
import { generalMessage } from '@/utils/authErrors'

const props = defineProps<{ bizno: string; watched: boolean; size?: 'sm' | 'md' }>()
const emit = defineEmits<{ changed: [boolean] }>()
const ui = useUiStore()
const queryClient = useQueryClient()
const busy = ref(false)

async function toggle() {
  busy.value = true
  try {
    if (props.watched) await competitorsApi.unwatch(props.bizno)
    else await competitorsApi.watch(props.bizno)
    ui.toast(props.watched ? copy.competitors.watchRemoved : copy.competitors.watchAdded, 'success')
    emit('changed', !props.watched)
    void queryClient.invalidateQueries({ queryKey: ['competitors'] })
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiButton
    :size="size ?? 'sm'"
    variant="secondary"
    :loading="busy"
    :aria-pressed="watched"
    :aria-label="watched ? copy.competitors.watchRemove : copy.competitors.watchAdd"
    data-watch
    @click="toggle"
  >
    <Star class="size-4" :class="watched ? 'fill-current text-warning-fg' : ''" aria-hidden="true" />
    <span>{{ watched ? copy.competitors.watchRemove : copy.competitors.watchAdd }}</span>
  </UiButton>
</template>

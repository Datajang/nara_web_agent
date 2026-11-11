<script setup lang="ts">
// 입력창 (SPEC §7.6, §10.4): Enter 전송, Shift+Enter 줄바꿈, 4,000자, 전송 중에는 [중지].
import { Send, Square } from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiTextarea from '@/components/ui/UiTextarea.vue'
import { copy } from '@/copy'

const props = withDefaults(defineProps<{ streaming?: boolean; maxLength?: number }>(), {
  streaming: false,
  maxLength: 4000,
})
const model = defineModel<string>({ default: '' })
const emit = defineEmits<{ send: [string]; stop: [] }>()

function submit() {
  const text = model.value.trim()
  if (!text || props.streaming) return
  emit('send', text)
  model.value = ''
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    submit()
  }
}
</script>

<template>
  <form class="flex flex-col gap-2" @submit.prevent="submit">
    <UiTextarea
      v-model="model"
      :label="copy.assistant.input"
      hide-label
      :rows="2"
      :max-length="maxLength"
      @keydown="onKey"
    />
    <div class="flex justify-end">
      <UiButton v-if="streaming" variant="secondary" @click="emit('stop')">
        <Square class="size-4" aria-hidden="true" />{{ copy.assistant.stop }}
      </UiButton>
      <UiButton v-else type="submit" :disabled="!model.trim()">
        <Send class="size-4" aria-hidden="true" />{{ copy.assistant.send }}
      </UiButton>
    </div>
  </form>
</template>

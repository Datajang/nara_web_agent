// 토스트 (SPEC §10.4 UiToast). 5초 뒤 사라지고 오류는 수동으로 닫는다.
import { defineStore } from 'pinia'
import { ref } from 'vue'

export type Tone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger'

export interface Toast {
  id: number
  tone: Tone
  message: string
}

export const useUiStore = defineStore('ui', () => {
  const toasts = ref<Toast[]>([])
  let seq = 0

  function toast(message: string, tone: Tone = 'neutral'): void {
    const id = ++seq
    toasts.value.push({ id, tone, message })
    if (tone !== 'danger') setTimeout(() => dismiss(id), 5000)
  }

  function dismiss(id: number): void {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }

  return { toasts, toast, dismiss }
})

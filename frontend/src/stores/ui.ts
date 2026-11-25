// 토스트 (SPEC §10.4 UiToast). 5초 뒤 사라지고 오류는 수동으로 닫는다.
// 사이드바 접기(2026-11-22): 넓은 화면에서 아이콘만 남기기. 브라우저마다 기억하고, 저장소가 막혀도 동작한다.
import { defineStore } from 'pinia'
import { ref } from 'vue'

export type Tone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger'

export interface Toast {
  id: number
  tone: Tone
  message: string
}

const SIDEBAR_KEY = 'nara.sidebar.collapsed'

function readSidebarCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === '1'
  } catch {
    return false
  }
}

export const useUiStore = defineStore('ui', () => {
  const toasts = ref<Toast[]>([])
  const sidebarCollapsed = ref(readSidebarCollapsed())

  function toggleSidebar(): void {
    sidebarCollapsed.value = !sidebarCollapsed.value
    try {
      localStorage.setItem(SIDEBAR_KEY, sidebarCollapsed.value ? '1' : '0')
    } catch {
      // 사생활 보호 창 등: 이번 화면에서만 유지
    }
  }
  let seq = 0

  function toast(message: string, tone: Tone = 'neutral'): void {
    const id = ++seq
    toasts.value.push({ id, tone, message })
    if (tone !== 'danger') setTimeout(() => dismiss(id), 5000)
  }

  function dismiss(id: number): void {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }

  // 북마크 결과 메일 안내 팝업(2026-11-25). watching=false면 개찰일 유무로 '정보 없음'·'너무 늦음' 문구
  const resultNotice = ref<{ watching: boolean; hasOpening: boolean } | null>(null)
  function showResultNotice(watching: boolean, hasOpening: boolean): void {
    resultNotice.value = { watching, hasOpening }
  }

  return {
    toasts,
    toast,
    dismiss,
    sidebarCollapsed,
    toggleSidebar,
    resultNotice,
    showResultNotice,
  }
})

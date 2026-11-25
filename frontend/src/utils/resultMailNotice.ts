// 북마크 결과 메일 안내 팝업 조건 (2026-11-25): 일반공고 ∧ 계정 전체 스위치 켬 ∧ '다시 보지 않기' 안 함.
// '다시 보지 않기'는 이 브라우저에만 저장한다(저장소가 막혀도 동작).
import type { BidCard, BookmarkPutOut } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

export const HIDE_KEY = 'nara.resultMailNotice.hide'

export function noticeHidden(): boolean {
  try {
    return localStorage.getItem(HIDE_KEY) === '1'
  } catch {
    return false
  }
}

export function hideNoticeForever(): void {
  try {
    localStorage.setItem(HIDE_KEY, '1')
  } catch {
    // 사생활 보호 창 등: 이번 화면에서만
  }
}

export function maybeShowResultNotice(bid: Pick<BidCard, 'source'>, res: BookmarkPutOut | null): void {
  const me = useAuthStore().me
  if (!res || bid.source !== 'regular' || me?.result_mail === false || noticeHidden()) return
  useUiStore().showResultNotice(res.watching, res.opening_at != null)
}

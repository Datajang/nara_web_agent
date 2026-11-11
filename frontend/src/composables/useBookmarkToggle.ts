// 카드의 북마크 토글. 목록의 bookmarked 표시를 바로 바꾸고, 실패하면 되돌린다.
import { useQueryClient } from '@tanstack/vue-query'
import type { Ref } from 'vue'
import { bidsApi } from '@/api/bids'
import type { BidCard } from '@/api/types'
import { copy } from '@/copy'
import { useUiStore } from '@/stores/ui'
import { generalMessage } from '@/utils/authErrors'

export function useBookmarkToggle(items: Ref<BidCard[]>) {
  const ui = useUiStore()
  const queryClient = useQueryClient()

  function mark(bidId: string, value: boolean) {
    items.value = items.value.map((b) => (b.bid_id === bidId ? { ...b, bookmarked: value } : b))
  }

  return async function toggle(bid: BidCard) {
    const next = !bid.bookmarked
    mark(bid.bid_id, next)
    try {
      if (next) await bidsApi.bookmark(bid.bid_id)
      else await bidsApi.unbookmark(bid.bid_id)
      ui.toast(next ? copy.bid.bookmarked : copy.bid.unbookmarked, 'success')
      void queryClient.invalidateQueries({ queryKey: ['bookmarks'] })
    } catch (e) {
      mark(bid.bid_id, !next)
      ui.toast(generalMessage(e), 'danger')
    }
  }
}

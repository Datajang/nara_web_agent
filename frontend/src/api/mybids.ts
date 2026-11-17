// 우리 투찰 결과(낙찰·탈락) API (P12, docs/decisions/2026-11-17-p12a-opening-ranks.md).
import { copy } from '@/copy'
import { api } from './client'
import type { components } from './schema'

type S = components['schemas']
export type MyBid = S['MyBidOut']
export type MyBidList = S['MyBidListOut']
export type MyBidDetail = S['MyBidDetailOut']
export type MyBidParticipant = S['MyBidParticipantOut']
export type MyBidFilter = 'all' | 'won' | 'lost'

export const myBidsApi = {
  list: (result: MyBidFilter, cursor?: string | null) => {
    const p = new URLSearchParams({ result })
    if (cursor) p.set('cursor', cursor)
    return api.get<MyBidList>(`/my-bids?${p.toString()}`)
  },
  detail: (k: MyBidKey) => api.get<MyBidDetail>(`/my-bids/${keyPath(k)}`),
}

export interface MyBidKey {
  bid_ntce_no: string
  bid_ntce_ord: string
  bid_clsfc_no: string
  rbid_no: string
}

export function keyPath(k: MyBidKey): string {
  return [k.bid_ntce_no, k.bid_ntce_ord, k.bid_clsfc_no, k.rbid_no].map(encodeURIComponent).join('/')
}

/** 결과 배지 글자와 색. 색만으로 뜻을 전하지 않도록 글자를 함께 쓴다. */
export function resultBadge(b: MyBid): { label: string; tone: 'success' | 'neutral' | 'warning' } {
  if (b.result === 'won') return { label: copy.myBids.won, tone: 'success' }
  if (b.result === 'lost') return { label: copy.myBids.lost, tone: 'neutral' }
  return { label: copy.myBids.disqualified, tone: 'warning' }
}

/** 순위 한 줄: 'N위 / 유효 k곳', 순위가 없으면 사유(비고), 개찰 결과 전이면 '순위는 상세에서'. */
export function rankText(b: MyBid): string {
  if (b.our_rank != null) return copy.myBids.rank(b.our_rank, b.valid_count ?? null)
  if (!b.fetched) return copy.myBids.rankLater
  if (b.result === 'won') return '' // 공동수급 구성원 등 개찰 결과에 우리 행이 없는 낙찰
  return b.remark ? `${copy.myBids.noRank} · ${b.remark}` : copy.myBids.noRank
}

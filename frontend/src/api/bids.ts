// 공고 검색·상세·북마크·피드백 API (SPEC §6.2·§6.3).
import { api, requestBlob } from './client'
import type { BidDetail, FeedbackIn, FileText, SearchQuery, SearchResult } from './types'

export const bidsApi = {
  search: (q: Partial<SearchQuery>) => api.post<SearchResult>('/bids/search', q),
  detail: (bidId: string) => api.get<BidDetail>(`/bids/${encodeURIComponent(bidId)}`),
  lookup: (bidNo: string) =>
    api.get<{ bid_id: string }>(`/bids/lookup?${new URLSearchParams({ bid_no: bidNo })}`),
  /** 입찰공고 목록 엑셀: 화면에 보이는 공고 ID를 순서대로 (2026-11-22) */
  exportList: (bidIds: string[]) => requestBlob('/bids/export', {}, { bid_ids: bidIds }),
  download: (bidId: string, fileId: number) =>
    requestBlob(`/bids/${encodeURIComponent(bidId)}/files/${fileId}/download`),
  fileText: (bidId: string, fileId: number, maxChars = 20000) =>
    api.get<FileText>(
      `/bids/${encodeURIComponent(bidId)}/files/${fileId}/text?max_chars=${maxChars}`,
    ),
  bookmark: (bidId: string, note = '', analysisId: number | null = null) =>
    api.put<void>(`/bookmarks/${encodeURIComponent(bidId)}`, { note, analysis_id: analysisId }),
  unbookmark: (bidId: string) => api.delete<void>(`/bookmarks/${encodeURIComponent(bidId)}`),
  feedback: (body: FeedbackIn) => api.post<{ id: number }>('/feedback', body),
}

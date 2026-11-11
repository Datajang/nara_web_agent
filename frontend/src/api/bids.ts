// 공고 검색·상세·북마크·피드백 API (SPEC §6.2·§6.3).
import { api } from './client'
import type { BidDetail, FeedbackIn, FileText, SearchQuery, SearchResult } from './types'

export const bidsApi = {
  search: (q: Partial<SearchQuery>) => api.post<SearchResult>('/bids/search', q),
  detail: (bidId: string) => api.get<BidDetail>(`/bids/${encodeURIComponent(bidId)}`),
  lookup: (bidNo: string) =>
    api.get<{ bid_id: string }>(`/bids/lookup?${new URLSearchParams({ bid_no: bidNo })}`),
  fileText: (bidId: string, fileId: number, maxChars = 20000) =>
    api.get<FileText>(
      `/bids/${encodeURIComponent(bidId)}/files/${fileId}/text?max_chars=${maxChars}`,
    ),
  bookmark: (bidId: string, note = '', analysisId: number | null = null) =>
    api.put<void>(`/bookmarks/${encodeURIComponent(bidId)}`, { note, analysis_id: analysisId }),
  unbookmark: (bidId: string) => api.delete<void>(`/bookmarks/${encodeURIComponent(bidId)}`),
  feedback: (body: FeedbackIn) => api.post<{ id: number }>('/feedback', body),
}

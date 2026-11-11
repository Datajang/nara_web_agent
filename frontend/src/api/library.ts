// 내 기록 API: 검색 기록·분석 기록·북마크 (SPEC §6.2, §7.7).
import { api } from './client'
import type {
  AnalysisDetail,
  AnalysisList,
  BookmarkList,
  SearchRunDetail,
  SearchRunList,
} from './types'

const qs = (o: Record<string, string | number | undefined>) =>
  new URLSearchParams(
    Object.entries(o)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => [k, String(v)]),
  ).toString()

export const libraryApi = {
  runs: (kind?: 'search' | 'recommend', limit = 50, offset = 0) =>
    api.get<SearchRunList>(`/search-runs?${qs({ kind, limit, offset })}`),
  run: (id: number, offset = 0, limit = 50) =>
    api.get<SearchRunDetail>(`/search-runs/${id}?${qs({ offset, limit })}`),
  deleteRun: (id: number) => api.delete<void>(`/search-runs/${id}`),
  analyses: (limit = 50, offset = 0) => api.get<AnalysisList>(`/analyses?${qs({ limit, offset })}`),
  analysis: (id: number) => api.get<AnalysisDetail>(`/analyses/${id}`),
  deleteAnalysis: (id: number) => api.delete<void>(`/analyses/${id}`),
  bookmarks: () => api.get<BookmarkList>('/bookmarks'),
}

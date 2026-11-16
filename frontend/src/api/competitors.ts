// 비교·경쟁사 레이더·관심 경쟁사·공고별 경쟁 구도 API (SPEC §15.6, P10·P11).
// AI 해설(POST /compare/{bizno}/explain)은 SSE라 useSse로 부른다.
import { api } from './client'
import type { components } from './schema'

type S = components['schemas']
export type Compare = S['CompareOut']
export type VerdictRow = S['VerdictOut']
export type Verdict = VerdictRow['verdict']
export type CandidateList = S['CandidateListOut']
export type Candidate = S['CandidateOut']
export type Watched = S['WatchedOut']
export type JointPartner = S['JointPartnerOut']
export type Competition = S['CompetitionOut']
export type CompetitionAward = S['CompetitionAwardOut']
export type Participant = S['ParticipantOut']
export type Spread = S['SpreadOut']

export const competitorsApi = {
  compare: (bizno: string) => api.get<Compare>(`/compare/${encodeURIComponent(bizno)}`),
  candidates: (q: { field?: string; org?: string; limit?: number } = {}) => {
    const p = new URLSearchParams()
    if (q.field) p.set('field', q.field)
    if (q.org) p.set('org', q.org)
    if (q.limit) p.set('limit', String(q.limit))
    const s = p.toString()
    return api.get<CandidateList>(`/competitors/candidates${s ? `?${s}` : ''}`)
  },
  watched: () => api.get<S['WatchedListOut']>('/competitors/watch'),
  watch: (bizno: string) => api.put<S['WatchedListOut']>(`/competitors/watch/${encodeURIComponent(bizno)}`),
  unwatch: (bizno: string) => api.delete<void>(`/competitors/watch/${encodeURIComponent(bizno)}`),
  competition: (bidId: string, limit = 5) =>
    api.get<Competition>(`/bids/${encodeURIComponent(bidId)}/competition?limit=${limit}`),
  explainPath: (bizno: string) => `/compare/${encodeURIComponent(bizno)}/explain`,
}

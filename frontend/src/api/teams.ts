// 팀·관심 공고 API (SPEC §13 P6).
import { api } from './client'
import type { components } from './schema'
import type { BidCard } from './types'

type S = components['schemas']
export type MyTeam = S['MyTeamOut']
export type TeamMember = S['MemberOut']
export type Feed = S['FeedOut']
/** 피드 카드 = 일반 카드 + 맞은 키워드. 응답의 점수 필드(선택)는 null로 채운다. */
export type FeedItem = BidCard & { matched_keywords: string[] }

export const teamsApi = {
  me: () => api.get<MyTeam>('/teams/me'),
  create: (name: string) => api.post<MyTeam>('/teams', { name } satisfies S['TeamIn']),
  join: (code: string) => api.post<MyTeam>('/teams/join', { code } satisfies S['JoinIn']),
  rename: (name: string) => api.patch<MyTeam>('/teams/me', { name } satisfies S['TeamIn']),
  rotateCode: () => api.post<MyTeam>('/teams/me/invite-code'),
  remove: (userId: number) => api.delete<void>(`/teams/me/members/${userId}`),
  leave: () => api.post<void>('/teams/me/leave'),
}

/** 관심 공고 안에서 좁히기 (2026-11-16). 비운 값은 보내지 않는다. */
export interface FeedFilter {
  q?: string
  source?: 'all' | 'regular' | 'prespec'
  kw?: string[]
}

export const feedApi = {
  get: async (offset = 0, limit = 20, filter: FeedFilter = {}) => {
    const p = new URLSearchParams({ offset: String(offset), limit: String(limit) })
    if (filter.q?.trim()) p.set('q', filter.q.trim())
    if (filter.source && filter.source !== 'all') p.set('source', filter.source)
    for (const k of filter.kw ?? []) p.append('kw', k)
    const f = await api.get<Feed>(`/feed?${p}`)
    const items: FeedItem[] = f.items.map((i) => ({ ...i, score: i.score ?? null, reason: i.reason ?? null }))
    return { ...f, items }
  },
}

/** 초대 링크: 같은 출처의 /join?code= (받는 사람이 로그인 뒤 수락). */
export function inviteLink(code: string): string {
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return `${origin}/join?code=${encodeURIComponent(code)}`
}

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

export const feedApi = {
  get: async (offset = 0, limit = 20) => {
    const f = await api.get<Feed>(`/feed?offset=${offset}&limit=${limit}`)
    const items: FeedItem[] = f.items.map((i) => ({ ...i, score: i.score ?? null, reason: i.reason ?? null }))
    return { ...f, items }
  },
}

/** 초대 링크: 같은 출처의 /join?code= (받는 사람이 로그인 뒤 수락). */
export function inviteLink(code: string): string {
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return `${origin}/join?code=${encodeURIComponent(code)}`
}

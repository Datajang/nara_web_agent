// 프로필 API (SPEC §6.2, §7.8).
import { api } from './client'
import type { Profile, ProfileIn, ProfilePatch } from './types'

export const profilesApi = {
  list: () => api.get<{ items: Profile[] }>('/profiles'),
  create: (body: ProfileIn) => api.post<Profile>('/profiles', body),
  update: (id: number, body: ProfilePatch) => api.patch<Profile>(`/profiles/${id}`, body),
  remove: (id: number) => api.delete<void>(`/profiles/${id}`),
  suggest: (description: string) =>
    api.post<{ keywords: string[] }>('/profiles/suggest-keywords', { description }),
}

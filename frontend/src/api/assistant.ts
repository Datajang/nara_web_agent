// 어시스턴트 대화 API (SPEC §6.2, §7.6). 메시지 전송은 useSse로 한다.
import { api } from './client'
import type { ChatMessage, Conversation } from './types'

export const assistantApi = {
  list: () => api.get<{ items: Conversation[] }>('/conversations'),
  create: (profileId: number | null) =>
    api.post<Conversation>('/conversations', { title: '', profile_id: profileId }),
  update: (id: number, body: { title?: string; profile_id?: number | null }) =>
    api.patch<Conversation>(`/conversations/${id}`, body),
  remove: (id: number) => api.delete<void>(`/conversations/${id}`),
  messages: (id: number) => api.get<{ items: ChatMessage[] }>(`/conversations/${id}/messages`),
}

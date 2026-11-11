// 인증·계정 API. 타입은 백엔드 OpenAPI에서 생성한 schema.d.ts를 쓴다(npm run gen:api).
import type { components } from './schema'
import { api } from './client'

type S = components['schemas']
export type Me = S['MeOut']
export type UserStatus = Me['status']
export type AdminUser = S['AdminUserOut']
export type AdminUserList = S['AdminUserList']

export const authApi = {
  me: () => api.get<Me>('/me', { silent: true }),
  login: (email: string, password: string) =>
    api.post<Me>('/auth/login', { email, password } satisfies S['LoginIn']),
  logout: () => api.post<void>('/auth/logout'),
  register: (body: S['RegisterIn']) => api.post<S['AcceptedOut']>('/auth/register', body),
  verifyEmail: (token: string) =>
    api.post<S['VerifyOut']>('/auth/verify-email', { token } satisfies S['TokenIn']),
  resendVerification: (email: string) =>
    api.post<S['AcceptedOut']>('/auth/verify-email/resend', { email } satisfies S['EmailIn']),
  forgotPassword: (email: string) =>
    api.post<S['AcceptedOut']>('/auth/password/forgot', { email } satisfies S['EmailIn']),
  resetPassword: (token: string, password: string) =>
    api.post<void>('/auth/password/reset', { token, password } satisfies S['ResetIn']),
}

export const adminApi = {
  users: (status: UserStatus, limit = 100, offset = 0) =>
    api.get<AdminUserList>(
      `/admin/users?${new URLSearchParams({ status, limit: String(limit), offset: String(offset) })}`,
    ),
  update: (id: number, patch: S['AdminUserPatch']) =>
    api.patch<AdminUser>(`/admin/users/${id}`, patch),
}

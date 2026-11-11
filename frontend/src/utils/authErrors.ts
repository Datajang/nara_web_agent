// 인증 API 오류 → 화면 문구. 로그인 실패는 이메일 존재 여부와 무관하게 하나로 (§7.10).
import { ApiError } from '@/api/client'
import { copy } from '@/copy'

const PASSWORD_REASONS: Record<string, string> = {
  too_short: copy.auth.passwordTooShort,
  too_long: copy.auth.passwordTooLong,
  too_common: copy.auth.passwordTooCommon,
}

export function passwordMessage(err: ApiError, field = 'password'): string | undefined {
  const reason = err.reason(field)
  return reason ? (PASSWORD_REASONS[reason] ?? copy.auth.invalidInput) : undefined
}

export function generalMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return copy.common.networkError
  if (err.status === 429) return copy.common.rateLimited(err.retryAfter ?? 60)
  if (err.status === 422) return copy.auth.invalidInput
  return copy.common.unknownError
}

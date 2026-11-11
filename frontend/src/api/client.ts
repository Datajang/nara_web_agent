// API 클라이언트 (SPEC §10.7). 쿠키 인증, 401이면 refresh를 한 번만(동시 요청 공유) 시도한다.

export const API_BASE = '/api/v1'

export interface ErrorDetail {
  field: string
  reason: string
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: ErrorDetail[] = [],
    readonly retryAfter: number | null = null,
  ) {
    super(message)
    this.name = 'ApiError'
  }

  reason(field: string): string | undefined {
    return this.details.find((d) => d.field === field)?.reason
  }
}

/** 앱이 연결하는 훅: 세션 만료 → 로그인 화면, 429 → 토스트. */
export const clientHooks: {
  onUnauthorized: () => void
  onRateLimited: (seconds: number) => void
} = {
  onUnauthorized: () => {},
  onRateLimited: () => {},
}

let refreshing: Promise<boolean> | null = null

/** 동시에 여러 번 불려도 refresh 요청은 하나. */
export function refreshOnce(): Promise<boolean> {
  refreshing ??= fetch(`${API_BASE}/auth/refresh`, { method: 'POST', credentials: 'include' })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null
    })
  return refreshing
}

export async function toApiError(res: Response): Promise<ApiError> {
  let body: { error?: { code?: string; message?: string; details?: ErrorDetail[] } } = {}
  try {
    body = await res.json()
  } catch {
    // 본문 없는 오류
  }
  const retry = res.headers.get('retry-after')
  return new ApiError(
    res.status,
    body.error?.code ?? 'error',
    body.error?.message ?? '',
    body.error?.details ?? [],
    retry ? Number(retry) : null,
  )
}

export interface RequestOptions {
  /** true면 refresh 실패 시 onUnauthorized를 부르지 않는다(첫 진입 /me 확인용). */
  silent?: boolean
  signal?: AbortSignal
  headers?: Record<string, string>
}

function send(method: string, path: string, body: unknown, opts: RequestOptions) {
  const headers = new Headers(opts.headers)
  if (body !== undefined) headers.set('content-type', 'application/json')
  return fetch(`${API_BASE}${path}`, {
    method,
    credentials: 'include',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: opts.signal,
  })
}

/** /auth/* 는 refresh 대상이 아니다(로그인 실패 401을 세션 만료로 오해하지 않게). */
export function needsRefresh(res: Response, path: string): boolean {
  return res.status === 401 && !path.startsWith('/auth/')
}

export async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  opts: RequestOptions = {},
): Promise<T> {
  let res = await send(method, path, body, opts)
  if (needsRefresh(res, path)) {
    if (await refreshOnce()) {
      res = await send(method, path, body, opts)
    }
    if (res.status === 401 && !opts.silent) clientHooks.onUnauthorized()
  }
  if (!res.ok) {
    const err = await toApiError(res)
    if (err.status === 429 && err.retryAfter) clientHooks.onRateLimited(err.retryAfter)
    throw err
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}

export const api = {
  get: <T>(path: string, opts?: RequestOptions) => request<T>('GET', path, undefined, opts),
  post: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>('POST', path, body, opts),
  patch: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>('PATCH', path, body, opts),
  put: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>('PUT', path, body, opts),
  delete: <T>(path: string, opts?: RequestOptions) => request<T>('DELETE', path, undefined, opts),
}

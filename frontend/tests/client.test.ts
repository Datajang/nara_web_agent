// §10.10-5: 401이면 refresh를 한 번만 부르고(동시 요청 공유) 원 요청을 재시도한다.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, clientHooks } from '@/api/client'

function json(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  clientHooks.onUnauthorized = () => {}
  clientHooks.onRateLimited = () => {}
})

describe('api client', () => {
  it('동시 요청 5개가 401이어도 refresh는 1번', async () => {
    let refreshed = false
    const fetchMock = vi.fn(async (url: string) => {
      if (url === '/api/v1/auth/refresh') {
        await new Promise((r) => setTimeout(r, 10))
        refreshed = true
        return json(200, { id: 1 })
      }
      return refreshed ? json(200, { ok: url }) : json(401, { error: { code: 'unauthorized' } })
    })
    vi.stubGlobal('fetch', fetchMock)
    const results = await Promise.all([1, 2, 3, 4, 5].map((i) => api.get(`/things/${i}`)))
    expect(results).toEqual([1, 2, 3, 4, 5].map((i) => ({ ok: `/api/v1/things/${i}` })))
    const refreshCalls = fetchMock.mock.calls.filter(([u]) => u === '/api/v1/auth/refresh')
    expect(refreshCalls).toHaveLength(1)
  })

  it('refresh가 실패하면 onUnauthorized 후 ApiError(401)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json(401, { error: { code: 'unauthorized', message: '', details: [] } })),
    )
    const onUnauthorized = vi.fn()
    clientHooks.onUnauthorized = onUnauthorized
    await expect(api.get('/me')).rejects.toMatchObject({ status: 401, code: 'unauthorized' })
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  it('silent 요청은 refresh 실패에도 onUnauthorized를 부르지 않는다', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(401, { error: { code: 'unauthorized' } })))
    const onUnauthorized = vi.fn()
    clientHooks.onUnauthorized = onUnauthorized
    await expect(api.get('/me', { silent: true })).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('/auth/* 요청은 401이어도 refresh하지 않는다', async () => {
    const fetchMock = vi.fn(async () =>
      json(401, { error: { code: 'invalid_credentials', message: 'x', details: [] } }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await expect(api.post('/auth/login', { email: 'a', password: 'b' })).rejects.toMatchObject({
      code: 'invalid_credentials',
    })
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('JSON 본문·쿠키 포함으로 보낸다', async () => {
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () =>
      json(201, { status: 'accepted' }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await api.post('/auth/register', { email: 'a@b.c' })
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(init.credentials).toBe('include')
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{"email":"a@b.c"}')
    expect(new Headers(init.headers).get('content-type')).toBe('application/json')
  })

  it('429는 Retry-After를 훅으로 알리고 ApiError에 담는다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        json(429, { error: { code: 'rate_limited', message: 'm', details: [] } }, { 'Retry-After': '42' }),
      ),
    )
    const onRateLimited = vi.fn()
    clientHooks.onRateLimited = onRateLimited
    await expect(api.post('/bids/search', {})).rejects.toMatchObject({ status: 429, retryAfter: 42 })
    expect(onRateLimited).toHaveBeenCalledWith(42)
  })

  it('204는 undefined', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 204 })))
    await expect(api.post('/auth/logout')).resolves.toBeUndefined()
  })
})

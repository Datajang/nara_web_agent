// §10.10-4: useSse — 정상 스트림, error, ping, 중간 끊김, abort, 첫 바이트 전 401.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useSse } from '@/composables/useSse'

type Ev = { type: string; stage?: string; [k: string]: unknown }

function stream(chunks: string[], { close = true, delayMs = 0 } = {}): ReadableStream<Uint8Array> {
  const enc = new TextEncoder()
  return new ReadableStream({
    async start(controller) {
      for (const c of chunks) {
        if (delayMs) await new Promise((r) => setTimeout(r, delayMs))
        controller.enqueue(enc.encode(c))
      }
      if (close) controller.close()
    },
  })
}

function sseResponse(body: ReadableStream<Uint8Array>, status = 200) {
  return new Response(body, { status, headers: { 'content-type': 'text/event-stream' } })
}

afterEach(() => vi.unstubAllGlobals())

describe('useSse', () => {
  it('정상 스트림: 청크가 이벤트 경계를 가로질러도 파싱하고 stage를 갱신', async () => {
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () =>
      sseResponse(
        stream([
          ': ping\n\n',
          'data: {"type":"status","stage":"collect"}\n\ndata: {"type":"sta',
          'tus","stage":"summarize"}\n\n',
          'event: result\r\ndata: {"items":[1]}\r\n\r\n',
          'data: {"type":"done"}\n\n',
        ]),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const sse = useSse<Ev>()
    await sse.start('/recommend', { profile_id: 1 })
    expect(sse.events.value.map((e) => e.type)).toEqual(['status', 'status', 'result', 'done'])
    expect(sse.events.value[2]).toEqual({ type: 'result', items: [1] })
    expect(sse.stage.value).toBe('summarize')
    expect(sse.streaming.value).toBe(false)
    expect(sse.error.value).toBeNull()
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/recommend')
    expect(new Headers(init.headers).get('accept')).toBe('text/event-stream')
    expect(init.method).toBe('POST')
  })

  it('error 이벤트는 error 상태로', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        sseResponse(
          stream(['data: {"type":"error","code":"llm_unavailable","message":"x"}\n\n', 'data: {"type":"done"}\n\n']),
        ),
      ),
    )
    const sse = useSse<Ev>()
    await sse.start('/x', {})
    expect(sse.error.value?.code).toBe('llm_unavailable')
  })

  it('done 없이 끊기면 오류 (자동 재연결 없음)', async () => {
    const fetchMock = vi.fn(async () => sseResponse(stream(['data: {"type":"status","stage":"a"}\n\n'])))
    vi.stubGlobal('fetch', fetchMock)
    const sse = useSse<Ev>()
    await sse.start('/x', {})
    expect(sse.error.value?.code).toBe('stream_interrupted')
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('abort하면 스트리밍만 멈추고 오류가 아니다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_u: string, init: RequestInit) => {
        const body = new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(new TextEncoder().encode('data: {"type":"status","stage":"a"}\n\n'))
            init.signal?.addEventListener('abort', () =>
              controller.error(new DOMException('aborted', 'AbortError')),
            )
          },
        })
        return sseResponse(body)
      }),
    )
    const sse = useSse<Ev>()
    const running = sse.start('/x', {})
    await new Promise((r) => setTimeout(r, 5))
    expect(sse.streaming.value).toBe(true)
    sse.abort()
    await running
    expect(sse.streaming.value).toBe(false)
    expect(sse.error.value).toBeNull()
    expect(sse.events.value).toHaveLength(1)
  })

  it('첫 바이트 전 401이면 refresh 후 한 번만 재시도', async () => {
    let calls = 0
    const fetchMock = vi.fn(async (url: string) => {
      if (url === '/api/v1/auth/refresh') return new Response('{}', { status: 200 })
      calls += 1
      if (calls === 1) return new Response('{"error":{"code":"unauthorized"}}', { status: 401 })
      return sseResponse(stream(['data: {"type":"done"}\n\n']))
    })
    vi.stubGlobal('fetch', fetchMock)
    const sse = useSse<Ev>()
    await sse.start('/x', {})
    expect(calls).toBe(2)
    expect(sse.error.value).toBeNull()
  })

  it('HTTP 오류 응답은 ApiError로', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{"error":{"code":"not_found","message":"","details":[]}}', { status: 404 })),
    )
    const sse = useSse<Ev>()
    await sse.start('/x', {})
    expect(sse.error.value?.status).toBe(404)
  })
})

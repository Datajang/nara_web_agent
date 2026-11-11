// SSE 훅 (SPEC §10.7). fetch POST + ReadableStream. 끊기면 자동 재연결 없이 오류로 둔다.
// 이벤트는 `data:` 줄의 JSON. `event:` 줄이 있으면 그 이름을 type으로 쓴다(§6.4는 P3에서 대조).
import { getCurrentInstance, onBeforeUnmount, ref, type Ref } from 'vue'
import { API_BASE, ApiError, needsRefresh, refreshOnce, toApiError } from '@/api/client'

export interface SseEvent {
  type: string
  stage?: string
  code?: string
  message?: string
}

export interface SseState<E> {
  events: Ref<E[]>
  stage: Ref<string | null>
  streaming: Ref<boolean>
  error: Ref<ApiError | null>
  start(path: string, body: unknown): Promise<void>
  abort(): void
}

export function parseEvent(block: string): SseEvent | null {
  let eventName: string | null = null
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (!line || line.startsWith(':')) continue // ping·주석
    const idx = line.indexOf(':')
    const field = idx === -1 ? line : line.slice(0, idx)
    const value = idx === -1 ? '' : line.slice(idx + 1).replace(/^ /, '')
    if (field === 'event') eventName = value
    else if (field === 'data') data.push(value)
  }
  if (!data.length) return null
  const parsed = JSON.parse(data.join('\n')) as Record<string, unknown>
  return { ...parsed, type: eventName ?? String(parsed.type ?? 'message') } as SseEvent
}

export function useSse<E extends SseEvent = SseEvent>(): SseState<E> {
  const events = ref([]) as Ref<E[]>
  const stage = ref<string | null>(null)
  const streaming = ref(false)
  const error = ref<ApiError | null>(null)
  let controller: AbortController | null = null

  const post = (path: string, body: unknown, signal: AbortSignal) =>
    fetch(`${API_BASE}${path}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'content-type': 'application/json', accept: 'text/event-stream' },
      body: JSON.stringify(body),
      signal,
    })

  async function start(path: string, body: unknown): Promise<void> {
    abort()
    const ctrl = new AbortController()
    controller = ctrl
    events.value = []
    stage.value = null
    error.value = null
    streaming.value = true
    let sawDone = false
    try {
      let res = await post(path, body, ctrl.signal)
      if (needsRefresh(res, path) && (await refreshOnce())) {
        res = await post(path, body, ctrl.signal) // 첫 바이트 전 401만 한 번 재시도
      }
      if (!res.ok || !res.body) {
        error.value = await toApiError(res)
        return
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true }).replace(/\r\n?/g, '\n')
        let idx: number
        while ((idx = buf.indexOf('\n\n')) >= 0) {
          const ev = parseEvent(buf.slice(0, idx))
          buf = buf.slice(idx + 2)
          if (!ev) continue
          events.value.push(ev as E)
          if (ev.type === 'status' && ev.stage) stage.value = ev.stage
          if (ev.type === 'error') {
            error.value = new ApiError(0, ev.code ?? 'error', ev.message ?? '')
          }
          if (ev.type === 'done') sawDone = true
        }
      }
      if (!sawDone && !error.value && !ctrl.signal.aborted) {
        error.value = new ApiError(0, 'stream_interrupted', '')
      }
    } catch (e) {
      if (!ctrl.signal.aborted) {
        error.value = e instanceof ApiError ? e : new ApiError(0, 'network_error', String(e))
      }
    } finally {
      if (controller === ctrl) {
        streaming.value = false
        controller = null
      }
    }
  }

  /** 화면의 스트리밍만 멈춘다. 서버 계산은 계속된다(§6.4). */
  function abort(): void {
    controller?.abort()
    controller = null
    streaming.value = false
  }

  if (getCurrentInstance()) onBeforeUnmount(abort)

  return { events, stage, streaming, error, start, abort }
}

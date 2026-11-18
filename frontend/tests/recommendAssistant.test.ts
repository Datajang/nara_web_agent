// §7.4 맞춤 추천, §7.6 AI 어시스턴트: SSE 진행·카드·액션·중지·오류.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { copy } from '@/copy'
import { card, json, mockApi, mountAt, profile, settle, sse, text, type Mounted } from './helpers'

let m: Mounted | null = null
beforeEach(() => {
  document.body.innerHTML = ''
})
afterEach(() => {
  m?.wrapper.unmount()
  m = null
  vi.unstubAllGlobals()
})

const DONE = { type: 'done', usage: { llm_calls: 0, g2b_calls: 0, cache: { score: true } } }

describe('RecommendView', () => {
  it('프로필이 없으면 만들기 안내', async () => {
    mockApi({ 'GET /api/v1/profiles': json({ items: [] }) })
    m = await mountAt('/recommend')
    expect(text(m.wrapper)).toContain(copy.recommend.noProfile)
    expect(m.wrapper.find('a[href="/settings/profiles"]').exists()).toBe(true)
  })

  it('기본 프로필로 추천: 진행 막대 → 점수 카드, 저장된 점수 안내', async () => {
    const api = mockApi({
      'GET /api/v1/profiles': json({ items: [profile({ id: 3, is_default: false }), profile()] }),
      'POST /api/v1/recommend': sse([
        { type: 'status', stage: 'search', message: '' },
        { type: 'status', stage: 'score', message: '', progress: { done: 1, total: 2 } },
        { type: 'status', stage: 'score', message: '', progress: { done: 2, total: 2 } },
        {
          type: 'cards',
          run_id: 9,
          items: [card({ score: 88, reason: '주력 일치' }), card({ bid_id: 'b2', score: 61, reason: '일부' })],
        },
        DONE,
      ]),
    })
    m = await mountAt('/recommend')
    await m.wrapper.findAll('button').find((b) => b.text() === copy.recommend.submit)!.trigger('click')
    await settle(10)
    expect(api.calls.find((c) => c.url === '/api/v1/recommend')?.body).toMatchObject({
      profile_id: 7,
      days: 14,
      top_n: 20,
    })
    const t = text(m.wrapper)
    expect(t).toContain('주력 일치')
    expect(t).toContain(copy.score.high)
    // 적합도는 왼쪽 칸에 숫자로, 막대는 쓰지 않는다 (2026-11-18 사용자 요청)
    expect(m.wrapper.findAll('[data-score]').map((x) => x.text())).toEqual([`88${copy.score.high}`, `61${copy.score.mid}`])
    expect(m.wrapper.findAll('[data-score] [role="progressbar"], [data-score] [style*="width"]')).toHaveLength(0)
    expect(t).toContain(copy.recommend.cached)
    expect(m.wrapper.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('2')
  })

  it('검토할 공고 수는 20~50건(기본 20), 고른 수만큼 후보·결과를 요청한다', async () => {
    const api = mockApi({
      'GET /api/v1/profiles': json({ items: [profile()] }),
      'POST /api/v1/recommend': sse([{ type: 'cards', run_id: 1, items: [] }, DONE]),
    })
    m = await mountAt('/recommend')
    const group = m.wrapper
      .findAll('fieldset')
      .find((f) => f.text().includes(copy.recommend.candidates))!
    const radios = group.findAll('input[type="radio"]')
    expect(radios.map((r) => (r.element as HTMLInputElement).value)).toEqual(['20', '30', '40', '50'])
    expect((radios[0]!.element as HTMLInputElement).checked).toBe(true)
    await radios[3]!.setValue(true)
    await m.wrapper.findAll('button').find((b) => b.text() === copy.recommend.submit)!.trigger('click')
    await settle(10)
    expect(api.calls.find((c) => c.url === '/api/v1/recommend')?.body).toMatchObject({
      candidates: 50,
      top_n: 50,
      include_small: false,
    })
  })

  it('1억 원 미만 사업은 기본으로 빼고, 체크하면 포함해 요청한다', async () => {
    const api = mockApi({
      'GET /api/v1/profiles': json({ items: [profile()] }),
      'POST /api/v1/recommend': sse([{ type: 'cards', run_id: 1, items: [] }, DONE]),
    })
    m = await mountAt('/recommend')
    expect(text(m.wrapper)).toContain(copy.recommend.minBudgetNote)
    const box = m.wrapper.get('input[name="recommend-small"]')
    expect((box.element as HTMLInputElement).checked).toBe(false)
    await box.setValue(true)
    expect(text(m.wrapper)).not.toContain(copy.recommend.minBudgetNote)
    await m.wrapper.findAll('button').find((b) => b.text() === copy.recommend.submit)!.trigger('click')
    await settle(10)
    expect(api.calls.find((c) => c.url === '/api/v1/recommend')?.body).toMatchObject({ include_small: true })
  })

  it('다른 화면에 다녀와도 추천 결과가 그대로 남는다', async () => {
    const api = mockApi({
      'GET /api/v1/profiles': json({ items: [profile()] }),
      'POST /api/v1/recommend': sse([
        { type: 'cards', run_id: 9, items: [card({ score: 88, reason: '주력 일치' })] },
        DONE,
      ]),
      'POST /api/v1/search': sse([DONE]),
    })
    m = await mountAt('/recommend')
    await m.wrapper.findAll('button').find((b) => b.text() === copy.recommend.submit)!.trigger('click')
    await settle(10)
    await m.router.push('/search')
    await settle()
    expect(text(m.wrapper)).not.toContain('주력 일치')
    await m.router.push('/recommend')
    await settle()
    expect(text(m.wrapper)).toContain('주력 일치')
    expect(api.calls.filter((c) => c.url === '/api/v1/recommend')).toHaveLength(1)
  })

  it('처음 열면 이 계정의 마지막 추천 기록과 조건을 불러온다', async () => {
    mockApi({
      'GET /api/v1/profiles': json({ items: [profile()] }),
      'GET /api/v1/search-runs': json({
        items: [{ id: 5, kind: 'recommend', profile_id: 7, query: {}, result_count: 1 }],
        total: 1,
      }),
      'GET /api/v1/search-runs/5': json({
        id: 5,
        kind: 'recommend',
        profile_id: 7,
        query: {
          days: 30,
          source: 'regular',
          candidates_max: 40,
          keywords: ['AI'],
          custom_keywords: false,
          include_small: true,
        },
        result_count: 1,
        data_as_of: null,
        from_cache: true,
        created_at: '2026-11-17T01:00:00Z',
        items: [card({ score: 72, reason: '지난 추천' })],
        offset: 0,
        limit: 50,
      }),
    })
    m = await mountAt('/recommend')
    await settle()
    const t = text(m.wrapper)
    expect(t).toContain('지난 추천')
    expect(t).toContain(copy.recommend.restored('').trim())
    const checked = m.wrapper
      .findAll('input[type="radio"]')
      .filter((r) => (r.element as HTMLInputElement).checked)
      .map((r) => (r.element as HTMLInputElement).value)
    expect(checked).toEqual(['regular', '30', '40']) // 구분·기간·검토 수 (구분도 2026-11-18부터 라디오)
    expect((m.wrapper.get('input[name="recommend-small"]').element as HTMLInputElement).checked).toBe(true)
  })
})

const CONV = {
  id: 4,
  title: 'AI 공고',
  profile_id: 7,
  created_at: '2026-11-09T00:00:00Z',
  updated_at: '2026-11-09T00:00:00Z',
}

function chatRoutes(stream: Response, extra: Record<string, unknown> = {}) {
  return {
    'GET /api/v1/conversations': json({ items: [CONV] }),
    'GET /api/v1/conversations/4/messages': json({ items: [] }),
    'GET /api/v1/profiles': json({ items: [profile()] }),
    'POST /api/v1/conversations/4/messages': stream,
    ...extra,
  }
}

async function send(w: Mounted['wrapper'], message: string) {
  await w.get('textarea').setValue(message)
  await w.get('textarea').trigger('keydown', { key: 'Enter' })
  await settle(10)
}

describe('AssistantView', () => {
  it('빈 대화는 추천 질문 칩, 보내면 토큰 스트리밍과 인라인 카드', async () => {
    const api = mockApi(
      chatRoutes(
        sse([
          { type: 'status', stage: 'search', message: '공고를 찾고 있어요' },
          { type: 'token', text: '찾은 공고예요: ' },
          { type: 'token', text: 'b101' },
          { type: 'cards', items: [card()] },
          { ...DONE, message_id: 77 },
        ]),
      ),
    )
    m = await mountAt('/assistant/4')
    for (const s of copy.assistant.suggestions) expect(text(m.wrapper)).toContain(s)
    await send(m.wrapper, 'AI 공고 찾아줘')
    expect(api.calls.find((c) => c.url.endsWith('/messages') && c.method === 'POST')?.body).toEqual({
      content: 'AI 공고 찾아줘',
    })
    const t = text(m.wrapper)
    expect(t).toContain('찾은 공고예요: b101')
    expect(m.wrapper.find('a[href="/bids/b101"]').exists()).toBe(true)
  })

  it('대화에 나온 공고는 오른쪽 칸에 중복 없이, 최근 답 것이 위로 모인다 (2026-11-18)', async () => {
    mockApi(
      chatRoutes(json({}), {
        'GET /api/v1/conversations/4/messages': json({
          items: [
            { role: 'user', content: '찾아줘', cards: [] },
            { role: 'assistant', content: '처음 답', cards: [card(), card({ bid_id: 'b102', title: '데이터 플랫폼' })] },
            { role: 'user', content: '더', cards: [] },
            { role: 'assistant', content: '다음 답', cards: [card({ bid_id: 'b103', title: '클라우드 전환' }), card()] },
          ],
        }),
      }),
    )
    m = await mountAt('/assistant/4')
    await settle()
    const aside = m.wrapper.get('[data-ref-cards]')
    expect(aside.findAll('h3').map((h) => h.text())).toEqual(['클라우드 전환', card().title, '데이터 플랫폼'])
    expect(aside.find(`button[aria-label="${copy.bid.bookmarkAdd}"]`).exists()).toBe(false)
  })

  it('도우미 답은 마크다운으로: 굵게·표, 질문은 글자 그대로', async () => {
    const answer =
      '**고액 공고 (10억 이상):** 없음\n\n| 공고 | 예산 |\n|---|---|\n| b101 | 302,727,273원 (약 3억 272만 원) |\n'
    mockApi(chatRoutes(sse([{ type: 'token', text: answer }, { ...DONE, message_id: 78 }])))
    m = await mountAt('/assistant/4')
    await send(m.wrapper, '**굵게** 보여 줘')
    const box = m.wrapper.get('[data-assistant-answer]')
    expect(box.get('strong').text()).toBe('고액 공고 (10억 이상):')
    expect(box.findAll('th').map((x) => x.text())).toEqual(['공고', '예산'])
    expect(box.findAll('td').map((x) => x.text())).toEqual(['b101', '302,727,273원 (약 3억 272만 원)'])
    expect(box.text()).not.toContain('**')
    expect(text(m.wrapper)).toContain('**굵게** 보여 줘') // 사용자 글은 해석하지 않는다
  })

  it('Shift+Enter는 줄바꿈, 4000자 제한과 글자 수', async () => {
    mockApi(chatRoutes(sse([DONE])))
    m = await mountAt('/assistant/4')
    const ta = m.wrapper.get('textarea')
    expect(ta.attributes('maxlength')).toBe('4000')
    await ta.setValue('가나')
    await ta.trigger('keydown', { key: 'Enter', shiftKey: true })
    expect(text(m.wrapper)).toContain(copy.common.chars(2, 4000))
  })

  it('action(open_tab)은 버튼으로 보여 주고 누르면 조건만 채워 이동한다', async () => {
    mockApi(
      chatRoutes(
        sse([
          { type: 'token', text: '검색 탭에서 보세요.' },
          { type: 'action', name: 'open_tab', params: { tab: 'search', keywords: ['AI'] } },
          DONE,
        ]),
      ),
    )
    m = await mountAt('/assistant/4')
    await send(m.wrapper, '검색 탭 열어줘')
    const btn = m.wrapper
      .findAll('button')
      .find((b) => b.text() === copy.assistant.openTab(copy.assistant.tabNames.search))!
    await btn.trigger('click')
    await vi.waitFor(() => expect(m!.router.currentRoute.value.path).toBe('/search'), { timeout: 3000 })
    expect(m.router.currentRoute.value.query).toMatchObject({ q: 'AI', prefill: '1' })
  })

  it('LLM 불가 오류는 말풍선 아래 안내와 다시 시도', async () => {
    let n = 0
    const api = mockApi(
      chatRoutes(sse([]), {
        'POST /api/v1/conversations/4/messages': () =>
          n++ === 0
            ? sse([{ type: 'error', code: 'llm_unavailable', message: copy.llm.unavailable }, DONE])
            : sse([{ type: 'token', text: '이제 돼요' }, DONE]),
      }),
    )
    m = await mountAt('/assistant/4')
    await send(m.wrapper, '안녕')
    expect(text(m.wrapper)).toContain(copy.llm.unavailable)
    await m.wrapper.findAll('button').find((b) => b.text() === copy.common.retry)!.trigger('click')
    await settle(10)
    const posts = api.calls.filter((c) => c.method === 'POST' && c.url.endsWith('/messages'))
    expect(posts.map((p) => p.body)).toEqual([{ content: '안녕' }, { content: '안녕' }])
    expect(text(m.wrapper)).toContain('이제 돼요')
  })

  it('전송 중에는 중지 버튼, 누르면 스트림만 멈춘다', async () => {
    mockApi(chatRoutes(sse([{ type: 'token', text: '천천히' }], { close: false })))
    m = await mountAt('/assistant/4')
    await send(m.wrapper, '느린 질문')
    const stop = m.wrapper.findAll('button').find((b) => b.text() === copy.assistant.stop)
    expect(stop).toBeTruthy()
    await stop!.trigger('click')
    await settle()
    expect(m.wrapper.findAll('button').some((b) => b.text() === copy.assistant.send)).toBe(true)
  })

  it('대화 프로필을 바꾸면 PATCH한다', async () => {
    const api = mockApi(
      chatRoutes(sse([DONE]), {
        'GET /api/v1/profiles': json({ items: [profile(), profile({ id: 8, name: '둘째 팀', is_default: false })] }),
        'PATCH /api/v1/conversations/4': json({ ...CONV, profile_id: 8 }),
      }),
    )
    m = await mountAt('/assistant/4')
    await m.wrapper.get(`select[aria-label="${copy.assistant.profile}"]`).setValue('8')
    await settle()
    expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ profile_id: 8 })
  })

  it('대화가 없을 때 보내면 기본 프로필로 대화를 만들고 그 주소로 이동한다', async () => {
    const api = mockApi({
      'GET /api/v1/conversations': json({ items: [] }),
      'GET /api/v1/profiles': json({ items: [profile()] }),
      'POST /api/v1/conversations': json({ ...CONV, title: '' }, 201),
      'GET /api/v1/conversations/4/messages': json({ items: [] }),
      'POST /api/v1/conversations/4/messages': sse([{ type: 'token', text: '네' }, DONE]),
    })
    m = await mountAt('/assistant')
    expect(text(m.wrapper)).toContain(copy.assistant.emptyList)
    await send(m.wrapper, '첫 질문')
    expect(api.calls.find((c) => c.url === '/api/v1/conversations' && c.method === 'POST')?.body).toEqual({
      title: '',
      profile_id: 7,
    })
    expect(m.router.currentRoute.value.path).toBe('/assistant/4')
    expect(text(m.wrapper)).toContain('네')
  })
})

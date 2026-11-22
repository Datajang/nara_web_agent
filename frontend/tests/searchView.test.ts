// §7.3 공고 검색: URL 동기화(§7.11-4), 최근 검색, 더 보기, 데이터 기준·수집 중, 빈·오류 상태, 북마크.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { copy } from '@/copy'
import { card, json, mockApi, mountAt, settle, text, type Mounted } from './helpers'

let m: Mounted | null = null
beforeEach(() => {
  document.body.innerHTML = ''
})
afterEach(() => {
  m?.wrapper.unmount()
  m = null
  vi.unstubAllGlobals()
})

const RESULT = {
  run_id: 41,
  data_as_of: '2026-11-09T01:20:00Z',
  incomplete: false,
  collecting: false,
  from_cache: true,
  total: 2,
  truncated: false,
  items: [card(), card({ bid_id: 'b102', title: '데이터 플랫폼', bookmarked: true })],
}
const RECENT = {
  items: [
    {
      id: 9,
      kind: 'search',
      profile_id: null,
      query: { keywords: ['클라우드'], days: 30, match: 'all' },
      result_count: 3,
      data_as_of: null,
      from_cache: true,
      created_at: '2026-11-09T00:00:00Z',
    },
  ],
  total: 1,
}

function routes(result: unknown = RESULT) {
  return {
    'POST /api/v1/bids/search': json(result),
    'GET /api/v1/search-runs': json(RECENT),
  }
}

describe('SearchView', () => {
  it('URL 조건으로 검색하고 폼에 복원한다 (§7.11-4)', async () => {
    const api = mockApi(routes())
    m = await mountAt('/search?q=AI,데이터&match=any&days=30&status=all&sort=deadline_asc')
    const body = api.calls.find((c) => c.url === '/api/v1/bids/search')?.body
    expect(body).toMatchObject({
      keywords: ['AI', '데이터'],
      match: 'any',
      days: 30,
      status: 'all',
      sort: 'deadline_asc',
      limit: 50,
    })
    const t = text(m.wrapper)
    expect(t).toContain('AI')
    expect(t).toContain('데이터')
    expect(t).toContain(copy.search.total(2))
    expect(t).toContain(copy.data.asOf('11-09 10:20'))
  })

  it('최소 예산은 기본 1억(10,000만원)이고 바꿀 수 있다', async () => {
    const api = mockApi(routes())
    m = await mountAt('/search?q=AI')
    const searches = () => api.calls.filter((c) => c.url === '/api/v1/bids/search')
    expect(searches()[0]!.body).toMatchObject({ budget_min: 100_000_000 })
    const min = m.wrapper.findAll('input[type="number"]')[0]!
    expect((min.element as HTMLInputElement).value).toBe('10000')
    expect(text(m.wrapper)).toContain(copy.search.budgetMinHint)

    await min.setValue('')
    await m.wrapper.get('form').trigger('submit')
    await settle()
    expect(m.router.currentRoute.value.query.bmin).toBe('')
    expect(searches().slice(-1)[0]!.body).not.toHaveProperty('budget_min')

    await m.router.push('/search?q=AI&bmin=5000')
    await settle()
    expect(searches().slice(-1)[0]!.body).toMatchObject({ budget_min: 50_000_000 })
  })

  it('예산 조건 없이 저장된 최근 검색은 기본 1억을 덧씌우지 않는다', async () => {
    const api = mockApi(routes())
    m = await mountAt('/search')
    await m.wrapper.findAll('button').find((b) => b.text().includes('클라우드'))!.trigger('click')
    await settle()
    const last = api.calls.filter((c) => c.url === '/api/v1/bids/search').slice(-1)[0]
    expect(last!.body).not.toHaveProperty('budget_min')
  })

  it('검색하면 조건이 URL에 반영된다', async () => {
    mockApi(routes())
    m = await mountAt('/search')
    const input = m.wrapper.get('input[aria-describedby]')
    await input.setValue('클라우드')
    await input.trigger('keydown', { key: 'Enter' })
    await m.wrapper.get('form').trigger('submit')
    await settle()
    expect(m.router.currentRoute.value.query.q).toBe('클라우드')
  })

  it('공고명으로도 찾는다: 입력 → URL(title) → 요청, 새로고침하면 복원 (2026-11-16)', async () => {
    const api = mockApi(routes())
    m = await mountAt('/search')
    const titled = '국가하천(낙동강, 내성천) 불법행위 단속 용역'
    await m.wrapper.get('input[name="title"]').setValue(titled)
    await m.wrapper.get('form').trigger('submit')
    await settle()
    expect(m.router.currentRoute.value.query.title).toBe(titled)
    const last = api.calls.filter((c) => c.url === '/api/v1/bids/search').slice(-1)[0]
    expect(last!.body).toMatchObject({ title: titled, keywords: [] })
    m.wrapper.unmount()

    mockApi(routes())
    m = await mountAt(`/search?title=${encodeURIComponent(titled)}`)
    expect((m.wrapper.get('input[name="title"]').element as HTMLInputElement).value).toBe(titled)
  })

  it('정렬은 결과 머리에서 바로 바꾸고 다시 검색한다, 조건 칸 이름표는 낭독기용 (2026-11-18)', async () => {
    const api = mockApi(routes())
    m = await mountAt('/search?q=AI')
    await m.wrapper.findAll('label').find((l) => l.text() === copy.search.sortDeadline)!.find('input').setValue(true)
    await settle()
    expect(m.router.currentRoute.value.query.sort).toBe('deadline_asc')
    expect(api.calls.filter((c) => c.url === '/api/v1/bids/search').slice(-1)[0]!.body).toMatchObject({
      sort: 'deadline_asc',
    })
    const form = m.wrapper.get('form#search-form')
    expect(form.findAll('label').find((l) => l.text() === copy.search.title)!.classes()).toContain('sr-only')
    expect(form.findAll('label').find((l) => l.text() === copy.search.keywords)!.classes()).toContain('sr-only')
  })

  it('최근 검색 칩에 공고명도 보인다', async () => {
    const withTitle = { ...RECENT, items: [{ ...RECENT.items[0]!, query: { keywords: [], title: '생육지원 데이터센터', days: 14 } }] }
    mockApi({ ...routes(), 'GET /api/v1/search-runs': json(withTitle) })
    m = await mountAt('/search')
    expect(text(m.wrapper)).toContain('생육지원 데이터센터')
  })

  it('최근 검색 칩을 누르면 조건을 채워 검색한다', async () => {
    const api = mockApi(routes())
    m = await mountAt('/search')
    const chip = m.wrapper.findAll('button').find((b) => b.text().includes('클라우드'))
    expect(chip).toBeTruthy()
    await chip!.trigger('click')
    await settle()
    const last = api.calls.filter((c) => c.url === '/api/v1/bids/search').slice(-1)[0]
    expect(last!.body).toMatchObject({ keywords: ['클라우드'], days: 30 })
  })

  it('더 보기는 스냅샷의 다음 페이지를 붙인다', async () => {
    const api = mockApi({
      ...routes({ ...RESULT, total: 3, items: RESULT.items }),
      'GET /api/v1/search-runs/41': json({
        ...RECENT.items[0],
        id: 41,
        items: [card({ bid_id: 'b103', title: '세 번째 공고' })],
        offset: 2,
        limit: 50,
      }),
    })
    m = await mountAt('/search?q=AI')
    const more = m.wrapper.findAll('button').find((b) => b.text() === copy.common.more)!
    await more.trigger('click')
    await settle()
    expect(api.calls.some((c) => c.url.startsWith('/api/v1/search-runs/41?offset=2'))).toBe(true)
    expect(text(m.wrapper)).toContain('세 번째 공고')
    expect(m.wrapper.findAll('button').some((b) => b.text() === copy.common.more)).toBe(false)
  })

  it('수집 중·일부 수집 중·500건 초과 안내', async () => {
    mockApi(routes({ ...RESULT, incomplete: true, collecting: true, truncated: true }))
    m = await mountAt('/search?q=AI')
    const t = text(m.wrapper)
    expect(t).toContain(copy.data.incomplete)
    expect(t).toContain(copy.data.collecting)
    expect(t).toContain(copy.search.truncated)
  })

  it('결과 0건이면 조건 완화 안내', async () => {
    mockApi(routes({ ...RESULT, total: 0, items: [] }))
    m = await mountAt('/search?q=없는말')
    expect(text(m.wrapper)).toContain(copy.search.empty)
  })

  it('오류면 메시지와 다시 시도', async () => {
    mockApi({ 'POST /api/v1/bids/search': json({ error: { code: 'x', message: '' } }, 500) })
    m = await mountAt('/search?q=AI')
    expect(text(m.wrapper)).toContain(copy.search.error)
    expect(m.wrapper.findAll('button').some((b) => b.text() === copy.common.retry)).toBe(true)
  })

  it('표 보기 전환과 북마크 토글', async () => {
    const api = mockApi({ ...routes(), 'PUT /api/v1/bookmarks/b101': json(null, 204) })
    m = await mountAt('/search?q=AI&view=table')
    expect(m.wrapper.find('table').exists()).toBe(true)
    await m.router.push('/search?q=AI')
    await settle()
    await m.wrapper.get(`button[aria-label="${copy.bid.bookmarkAdd}"]`).trigger('click')
    await settle()
    expect(api.calls.some((c) => c.method === 'PUT' && c.url === '/api/v1/bookmarks/b101')).toBe(true)
    expect(m.wrapper.findAll(`button[aria-label="${copy.bid.bookmarkRemove}"]`)).toHaveLength(2)
  })

  it('어시스턴트에서 넘어온 조건(prefill=1)은 자동 검색하지 않는다 (§7.6)', async () => {
    const api = mockApi(routes())
    m = await mountAt('/search?q=AI&prefill=1')
    expect(api.calls.some((c) => c.url === '/api/v1/bids/search')).toBe(false)
    expect(text(m.wrapper)).toContain('AI')
  })
})

describe('입찰공고 목록 다운로드 (2026-11-22)', () => {
  it('결과 머리의 목록 다운로드는 화면의 공고 ID를 순서대로 보낸다', async () => {
    const api = mockApi({
      ...routes(),
      'POST /api/v1/bids/export': () => new Response('x', { status: 200 }),
    })
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} }))
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    m = await mountAt('/search?q=AI')
    await settle()
    await m.wrapper.get('[data-export]').trigger('click')
    await settle()
    const call = api.calls.find((c) => c.url === '/api/v1/bids/export')!
    expect(call.body).toEqual({ bid_ids: ['b101', 'b102'] })
  })
})

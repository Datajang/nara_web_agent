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

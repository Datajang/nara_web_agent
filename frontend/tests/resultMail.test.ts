// 북마크 공고 결과 메일 (2026-11-25, 계획 Task 10): 북마크 팝업, 보관함 공고별 켜기/끄기, 계정 전체 스위치.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { copy } from '@/copy'
import { MEMBER, card, json, mockApi, mountAt, settle, type Mounted } from './helpers'

let m: Mounted | null = null
beforeEach(() => {
  document.body.innerHTML = ''
  localStorage.clear()
})
afterEach(() => {
  m?.wrapper.unmount()
  m = null
  vi.unstubAllGlobals()
})

const WATCHING = { notify_result: true, watching: true, opening_at: '2026-11-20T01:00:00Z' }

function feed(...cards: ReturnType<typeof card>[]) {
  return json({
    keywords: ['AI'],
    needs_keywords: false,
    total: cards.length,
    items: cards.map((c) => ({ ...c, matched_keywords: ['AI'] })),
  })
}

async function bookmarkFirst(): Promise<void> {
  const btns = m!.wrapper.findAll(`button[aria-label="${copy.bid.bookmarkAdd}"]`)
  await btns[0]!.trigger('click')
  await settle()
}

const body = () => document.body.textContent ?? ''

describe('북마크 결과 메일 팝업', () => {
  it('일반공고를 북마크하면 결과 메일 안내 팝업을 띄운다', async () => {
    mockApi({ 'GET /api/v1/feed': feed(card()), 'PUT /api/v1/bookmarks/b101': json(WATCHING) })
    m = await mountAt('/')
    await bookmarkFirst()
    expect(body()).toContain(copy.resultMail.noticeTitle)
    expect(body()).toContain(MEMBER.email)
  })

  it('사전규격은 팝업을 띄우지 않는다', async () => {
    mockApi({
      'GET /api/v1/feed': feed(card({ source: 'prespec' })),
      'PUT /api/v1/bookmarks/b101': json({ ...WATCHING, watching: false, opening_at: null }),
    })
    m = await mountAt('/')
    await bookmarkFirst()
    expect(body()).not.toContain(copy.resultMail.noticeTitle)
  })

  it('전체 스위치를 끈 사람에게는 팝업을 띄우지 않는다', async () => {
    mockApi(
      { 'GET /api/v1/feed': feed(card()), 'PUT /api/v1/bookmarks/b101': json(WATCHING) },
      { ...MEMBER, result_mail: false },
    )
    m = await mountAt('/')
    await bookmarkFirst()
    expect(body()).not.toContain(copy.resultMail.noticeTitle)
  })

  it('개찰일이 없어 지켜볼 수 없으면 그 사실을 알린다', async () => {
    mockApi({
      'GET /api/v1/feed': feed(card()),
      'PUT /api/v1/bookmarks/b101': json({ ...WATCHING, watching: false, opening_at: null }),
    })
    m = await mountAt('/')
    await bookmarkFirst()
    expect(body()).toContain(copy.resultMail.noticeNoOpening)
  })

  it('"다시 보지 않기"를 고르면 이 브라우저에서는 다시 띄우지 않는다', async () => {
    mockApi({
      'GET /api/v1/feed': feed(card(), card({ bid_id: 'b102', title: '두 번째' })),
      'PUT /api/v1/bookmarks/b101': json(WATCHING),
      'PUT /api/v1/bookmarks/b102': json(WATCHING),
    })
    m = await mountAt('/')
    await bookmarkFirst()
    const hide = document.body.querySelector<HTMLInputElement>('input[name="result-mail-hide"]')!
    hide.click()
    document.body.querySelector<HTMLButtonElement>('[data-result-mail-ok]')!.click()
    await settle()
    expect(localStorage.getItem('nara.resultMailNotice.hide')).toBe('1')
    await bookmarkFirst()
    expect(body()).not.toContain(copy.resultMail.noticeTitle)
  })
})

describe('결과 메일 켜기·끄기', () => {
  it('보관함에서 공고마다 결과 메일을 끈다(일반공고만 보인다)', async () => {
    const api = mockApi({
      'GET /api/v1/bookmarks': json({
        items: [
          { bid: card({ bookmarked: true }), note: '', analysis_id: null, created_at: '2026-11-09T00:00:00Z', notify_result: true },
          {
            bid: card({ bid_id: 'b2', source: 'prespec', bookmarked: true }),
            note: '',
            analysis_id: null,
            created_at: '2026-11-08T00:00:00Z',
            notify_result: true,
          },
        ],
      }),
      'PATCH /api/v1/bookmarks/b101': json({ ...WATCHING, notify_result: false }),
    })
    m = await mountAt('/library?tab=bookmarks')
    await settle()
    const toggles = m.wrapper.findAll('input[name="result-mail"]')
    expect(toggles).toHaveLength(1)
    await toggles[0]!.setValue(false)
    await settle()
    const call = api.calls.find((c) => c.method === 'PATCH')
    expect(call?.url).toBe('/api/v1/bookmarks/b101')
    expect(call?.body).toEqual({ notify_result: false })
  })

  it('계정 설정의 전체 스위치는 내 정보에 저장한다', async () => {
    const api = mockApi({ 'PATCH /api/v1/me': json({ ...MEMBER, result_mail: false }) }, {
      ...MEMBER,
      result_mail: true,
    })
    m = await mountAt('/settings/account')
    await settle()
    const sw = m.wrapper.get('input[name="result-mail-all"]')
    expect((sw.element as HTMLInputElement).checked).toBe(true)
    await sw.setValue(false)
    await settle()
    const call = api.calls.find((c) => c.method === 'PATCH')
    expect(call?.body).toEqual({ result_mail: false })
  })
})

// §7.7 내 기록, §7.8 설정, §7.9 관리자 사용량·수집기, 403 화면(§7.11-9), 화면별 axe(§10.10-7).
import axe from 'axe-core'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { copy } from '@/copy'
import { ADMIN, card, json, mockApi, mountAt, profile, settle, text, type Mounted } from './helpers'

vi.mock('vue-chartjs', () => ({ Line: { name: 'Line', template: '<canvas />', props: ['data', 'options'] } }))

let m: Mounted | null = null
beforeEach(() => {
  document.body.innerHTML = ''
})
afterEach(() => {
  m?.wrapper.unmount()
  m = null
  vi.unstubAllGlobals()
})

const RUN = {
  id: 9,
  kind: 'search',
  profile_id: null,
  query: { keywords: ['클라우드'], days: 30 },
  result_count: 1,
  data_as_of: null,
  from_cache: true,
  created_at: '2026-11-09T00:00:00Z',
}
const BOOKMARKS = {
  items: [
    { bid: card({ bookmarked: true }), note: '검토', analysis_id: 5, created_at: '2026-11-09T00:00:00Z' },
    {
      bid: card({ bid_id: 'b2', title: '도로 공사', deadline_at: '2026-11-12T00:00:00Z', bookmarked: true }),
      note: '',
      analysis_id: null,
      created_at: '2026-11-08T00:00:00Z',
    },
  ],
}

describe('LibraryView', () => {
  it('탭은 URL과 동기화되고 검색 기록 스냅샷을 외부 호출 없이 연다', async () => {
    const api = mockApi({
      'GET /api/v1/search-runs': json({ items: [RUN], total: 1 }),
      'GET /api/v1/search-runs/9': json({ ...RUN, items: [card()], offset: 0, limit: 50 }),
    })
    m = await mountAt('/library')
    expect(m.router.currentRoute.value.path).toBe('/library')
    await m.wrapper.findAll('button').find((b) => b.text() === copy.library.open)!.trigger('click')
    await settle()
    expect(text(m.wrapper)).toContain(card().title)
    expect(api.calls.some((c) => c.url.includes('/bids/search'))).toBe(false)
    await m.wrapper.findAll('button').find((b) => b.text() === copy.library.rerun)!.trigger('click')
    // /search는 지연 로딩 라우트라 첫 import가 settle()보다 늦을 수 있다: 이동 완료를 기다린다
    await vi.waitFor(() => expect(m!.router.currentRoute.value.path).toBe('/search'), { timeout: 5000 })
    expect(m.router.currentRoute.value.query).toMatchObject({ q: '클라우드', days: '30' })
  })

  it('분석 기록: 프로필 이름, 상세 링크, 내 기록에서만 제거', async () => {
    const api = mockApi({
      'GET /api/v1/analyses': json({
        items: [
          {
            analysis_id: 5,
            bid: card(),
            profile_id: 7,
            profile_name: '우리 팀',
            fit_score: 82,
            verdict: 'strong',
            created_at: '2026-11-09T00:00:00Z',
          },
        ],
        total: 1,
      }),
      'DELETE /api/v1/analyses/5': json(null, 204),
    })
    m = await mountAt('/library?tab=analyses')
    expect(text(m.wrapper)).toContain('우리 팀')
    expect(m.wrapper.find('a[href="/bids/b101?analysis=5"]').exists()).toBe(true)
    await m.wrapper.findAll('button').find((b) => b.text() === copy.library.remove)!.trigger('click')
    await settle()
    expect(api.calls.some((c) => c.method === 'DELETE' && c.url === '/api/v1/analyses/5')).toBe(true)
  })

  it('북마크: 메모 저장, 제목 검색, 마감 임박순', async () => {
    const api = mockApi({
      'GET /api/v1/bookmarks': json(BOOKMARKS),
      'PUT /api/v1/bookmarks/b101': json(null, 204),
    })
    m = await mountAt('/library?tab=bookmarks')
    const note = m.wrapper.findAll('textarea')[0]!
    await note.setValue('다시 검토')
    await m.wrapper.findAll('button').find((b) => b.text() === copy.library.noteSave)!.trigger('click')
    await settle()
    expect(api.calls.find((c) => c.method === 'PUT')?.body).toEqual({ note: '다시 검토', analysis_id: 5 })

    await m.wrapper.get(`select[aria-label="${copy.library.sort}"]`).setValue('deadline')
    await settle()
    const titles = m.wrapper.findAll('h3').map((h) => h.text())
    expect(titles[0]).toContain('도로 공사')
    await m.wrapper.get(`input[aria-label="${copy.library.filterTitle}"]`).setValue('AI')
    await settle()
    expect(text(m.wrapper)).not.toContain('도로 공사')
  })
})

describe('Settings', () => {
  it('프로필: 키워드 제안으로 칩을 채우고 저장한다', async () => {
    const api = mockApi({
      'GET /api/v1/profiles': json({ items: [] }),
      'POST /api/v1/profiles/suggest-keywords': json({ keywords: ['인공지능', 'AI'] }),
      'POST /api/v1/profiles': json(profile(), 201),
    })
    m = await mountAt('/settings/profiles')
    expect(text(m.wrapper)).toContain(copy.profile.empty)
    await m.wrapper.findAll('button').find((b) => b.text() === copy.profile.newProfile)!.trigger('click')
    await settle()
    const inputs = m.wrapper.findAll('input')
    await inputs[0]!.setValue('AI 팀')
    const desc = '인공지능 검색 플랫폼을 만듭니다'
    await m.wrapper.get('textarea').setValue(desc)
    expect(text(m.wrapper)).toContain(copy.common.chars(desc.length, 4000))
    await m.wrapper.findAll('button').find((b) => b.text() === copy.profile.suggest)!.trigger('click')
    await settle()
    expect(text(m.wrapper)).toContain('인공지능')
    await m.wrapper.get('form').trigger('submit')
    await settle()
    expect(api.calls.find((c) => c.method === 'POST' && c.url === '/api/v1/profiles')?.body).toMatchObject({
      name: 'AI 팀',
      description: '인공지능 검색 플랫폼을 만듭니다',
      keywords: ['인공지능', 'AI'],
    })
  })

  it('설명을 바꾸면 재계산 안내, 삭제는 확인 모달', async () => {
    const api = mockApi({
      'GET /api/v1/profiles': json({ items: [profile()] }),
      'DELETE /api/v1/profiles/7': json(null, 204),
    })
    m = await mountAt('/settings/profiles')
    await m.wrapper.findAll('button').find((b) => b.text() === copy.profile.edit)!.trigger('click')
    await settle()
    await m.wrapper.get('textarea').setValue('완전히 새 설명')
    expect(text(m.wrapper)).toContain(copy.profile.changed)
    await m.wrapper.findAll('button').find((b) => b.text() === copy.common.remove)!.trigger('click')
    await settle()
    expect(document.body.textContent).toContain(copy.profile.removeTitle)
    const confirm = Array.from(document.querySelectorAll('[role="dialog"] button')).find(
      (b) => b.textContent === copy.common.confirm,
    ) as HTMLButtonElement
    confirm.click()
    await settle()
    expect(api.calls.some((c) => c.method === 'DELETE')).toBe(true)
  })

  it('계정: 이름 저장', async () => {
    const api = mockApi({ 'PATCH /api/v1/me': json({ id: 1, email: 'a@corp.example', display_name: '새 이름', role: 'member', status: 'active' }) })
    m = await mountAt('/settings/account')
    const forms = m.wrapper.findAll('form')
    await forms[0]!.get('input').setValue('새 이름')
    await forms[0]!.trigger('submit')
    await settle()
    expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ display_name: '새 이름' })
  })
})

describe('Admin', () => {
  it('일반 회원이 /admin/*에 오면 403 화면', async () => {
    mockApi({})
    m = await mountAt('/admin/usage')
    expect(text(m.wrapper)).toContain(copy.page.forbiddenTitle)
  })

  it('사용량: 합계 카드와 계층별 적중률', async () => {
    mockApi(
      {
        'GET /api/v1/admin/usage': json({
          items: [
            { day: '2026-11-09', event: 'search', requests: 4, g2b_calls: 10, llm_calls: 0, prompt_tokens: 0, completion_tokens: 0, hit_rate: { bids_db: 0.75, file_text: null, summary: null, analysis: null, score: null } },
            { day: '2026-11-09', event: 'analyze', requests: 2, g2b_calls: 0, llm_calls: 3, prompt_tokens: 1200, completion_tokens: 300, hit_rate: { bids_db: null, file_text: 0.5, summary: 0.5, analysis: 0.5, score: null } },
          ],
        }),
      },
      ADMIN,
    )
    m = await mountAt('/admin/usage')
    const t = text(m.wrapper)
    expect(t).toContain(copy.admin.g2bCalls)
    expect(t).toContain('10')
    expect(t).toContain('1,200')
    expect(t).toContain('75%')
  })

  it('사용량: 피드백 사유별 집계(👎 많은 순) (§12.7-2)', async () => {
    mockApi(
      {
        'GET /api/v1/admin/usage': json({
          items: [
            { day: '2026-11-09', event: 'analyze', requests: 2, g2b_calls: 0, llm_calls: 3, prompt_tokens: 1, completion_tokens: 1, hit_rate: { bids_db: null, file_text: null, summary: null, analysis: null, score: null } },
          ],
          feedback: [
            { target_type: 'analysis', rating: -1, reason: 'missing', count: 5 },
            { target_type: 'assistant_message', rating: -1, reason: 'wrong', count: 2 },
            { target_type: 'analysis', rating: 1, reason: null, count: 9 },
          ],
        }),
      },
      ADMIN,
    )
    m = await mountAt('/admin/usage')
    const table = m.wrapper.get(`table[aria-label="${copy.admin.feedbackTitle}"]`)
    const rows = table.findAll('tbody tr').map((r) => r.text())
    expect(rows[0]).toContain(copy.feedback.reasons.missing)
    expect(rows[0]).toContain(copy.admin.feedbackTargets.analysis)
    expect(rows[0]).toContain('5')
    expect(rows[1]).toContain(copy.feedback.reasons.wrong)
    expect(rows).toHaveLength(2) // 👍는 표 아래 합계로만
    expect(text(m.wrapper)).toContain(copy.admin.feedbackUp(9))
  })

  it('수집기: 범위·최근 실행, 수동 실행은 확인 후', async () => {
    const api = mockApi(
      {
        'GET /api/v1/admin/collector/runs': json({
          items: [
            { id: 1, source: 'regular', mode: 'incremental', window_from: '2026-11-08T00:00:00Z', window_to: '2026-11-09T00:00:00Z', status: 'ok', fetched: 20, inserted: 5, updated: 1, g2b_calls: 2, error: null, started_at: '2026-11-09T00:00:00Z', finished_at: '2026-11-09T00:01:00Z' },
          ],
          coverage: [
            { source: 'regular', covered_from: '2026-08-11T00:00:00Z', covered_to: '2026-11-09T00:00:00Z', updated_at: '2026-11-09T00:00:00Z' },
          ],
        }),
        'POST /api/v1/admin/collector/run': json({ status: 'accepted' }, 202),
      },
      ADMIN,
    )
    m = await mountAt('/admin/collector')
    const t = text(m.wrapper)
    expect(t).toContain(copy.admin.runStatus.ok)
    expect(t).toContain('2026-08-11')
    await m.wrapper.get('form').trigger('submit')
    await settle()
    expect(api.calls.some((c) => c.method === 'POST')).toBe(false) // 확인 전에는 실행 안 함
    const confirm = Array.from(document.querySelectorAll('[role="dialog"] button')).find(
      (b) => b.textContent === copy.common.confirm,
    ) as HTMLButtonElement
    confirm.click()
    await settle()
    expect(api.calls.find((c) => c.method === 'POST')?.body).toMatchObject({ mode: 'incremental', source: 'regular' })
  })
})

describe('접근성 (axe)', () => {
  const pages: Array<[string, Record<string, ReturnType<typeof json>>]> = [
    ['/search', { 'POST /api/v1/bids/search': json({ run_id: 1, data_as_of: null, incomplete: false, collecting: false, from_cache: true, total: 1, truncated: false, items: [card()] }), 'GET /api/v1/search-runs': json({ items: [], total: 0 }) }],
    ['/recommend', { 'GET /api/v1/profiles': json({ items: [profile()] }) }],
    ['/assistant', { 'GET /api/v1/conversations': json({ items: [] }), 'GET /api/v1/profiles': json({ items: [profile()] }) }],
    ['/library?tab=bookmarks', { 'GET /api/v1/bookmarks': json(BOOKMARKS) }],
    ['/settings/profiles', { 'GET /api/v1/profiles': json({ items: [profile()] }) }],
    ['/settings/account', {}],
  ]
  it.each(pages)('%s: critical·serious 위반 없음', async (path, routes) => {
    mockApi(routes)
    m = await mountAt(path)
    const result = await axe.run(m.wrapper.element as HTMLElement, {
      rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    })
    const bad = result.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious')
    expect(bad.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(' | ')}`)).toEqual([])
  })
})

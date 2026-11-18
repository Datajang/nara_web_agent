// P6 화면 (SPEC §13 P6): 관심 공고 홈, 키워드 설정, 초대 수락, 팀 설정, 팀 분석.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { copy } from '@/copy'
import type { VueWrapper } from '@vue/test-utils'
import { card, json, MEMBER, mockApi, mountAt, profile, settle, text, type Mounted } from './helpers'

/** <label for>로 이어진 입력을 라벨 글자로 찾는다. */
function byLabel(w: VueWrapper, label: string) {
  const l = w.findAll('label').find((x) => x.text() === label)
  if (!l) throw new Error(`label not found: ${label}`)
  return w.get(`[id="${l.attributes('for')}"]`)
}

let m: Mounted | null = null
beforeEach(() => {
  document.body.innerHTML = ''
})
afterEach(() => {
  m?.wrapper.unmount()
  m = null
  vi.unstubAllGlobals()
})

const TEAM = { id: 3, name: 'AI 플랫폼팀', invite_code: 'ABCD234567' }
const OWNER = { user_id: 1, display_name: '에이', role: 'owner', joined_at: '2026-11-01T00:00:00Z' }
const MATE = { user_id: 2, display_name: '비', role: 'member', joined_at: '2026-11-02T00:00:00Z' }
const myTeam = (role: 'owner' | 'member') => ({ team: TEAM, role, members: [OWNER, MATE] })
const NO_TEAM = { team: null, role: null, members: [] }

describe('관심 공고 홈 (/)', () => {
  it('키워드와 맞은 공고를 보여 주고, 공고마다 맞은 키워드를 단다', async () => {
    mockApi({
      'GET /api/v1/feed': json({
        keywords: ['클라우드', 'AI 플랫폼', '데이터'],
        needs_keywords: false,
        total: 1,
        items: [{ ...card({ title: '공공 데이터 품질 관리' }), matched_keywords: ['데이터'] }],
      }),
    })
    m = await mountAt('/')
    const t = text(m.wrapper)
    expect(m.router.currentRoute.value.path).toBe('/')
    for (const s of ['클라우드', 'AI 플랫폼', '공공 데이터 품질 관리', copy.feed.title]) expect(t).toContain(s)
    expect(m.wrapper.get('[data-matched]').text()).toBe('데이터')
  })

  it('기본은 1억 원 이상만, "1억 원 미만도 보기"를 켜면 계정에 저장하고 다시 불러온다 (2026-11-16)', async () => {
    let small = false
    const api = mockApi({
      'GET /api/v1/feed': () =>
        json({
          keywords: ['AI', '데이터', '클라우드'],
          needs_keywords: false,
          total: small ? 2 : 1,
          min_budget: small ? null : 100_000_000,
          items: [
            { ...card({ title: '큰 사업' }), matched_keywords: ['AI'] },
            ...(small ? [{ ...card({ bid_id: 'b109', title: '작은 사업' }), matched_keywords: ['AI'] }] : []),
          ],
        }),
      'PATCH /api/v1/me': () => {
        small = true
        return json({ ...MEMBER, feed_include_small: true })
      },
    })
    m = await mountAt('/')
    const box = m.wrapper.get('input[name="feed-small"]')
    expect((box.element as HTMLInputElement).checked).toBe(false)
    expect(text(m.wrapper)).toContain(copy.feed.includeSmall)
    expect(text(m.wrapper)).not.toContain('작은 사업')
    await box.setValue(true)
    await settle()
    expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ feed_include_small: true })
    expect(text(m.wrapper)).toContain('작은 사업')
  })

  describe('관심 공고 안에서 좁혀 보기 (2026-11-16)', () => {
    const KW = ['클라우드', 'AI 플랫폼', '데이터']
    /** 요청 URL의 쿼리를 읽어 걸러 준다: source·kw·q·due(마감 보드 칸) */
    function feedRoute() {
      const all = [
        { ...card({ bid_id: 'b1', title: '클라우드 전환 컨설팅' }), source: 'regular', matched_keywords: ['클라우드'], due: 'today' },
        { ...card({ bid_id: 'b2', title: 'AI 플랫폼 운영 사전규격' }), source: 'prespec', matched_keywords: ['AI 플랫폼'], due: 'd3' },
        { ...card({ bid_id: 'b3', title: '공공 데이터 품질 관리' }), source: 'regular', matched_keywords: ['데이터'], due: 'later' },
      ]
      return (_: RequestInit, url: string) => {
        const p = new URL(url, 'http://x').searchParams
        const kw = p.getAll('kw')
        const items = all.filter(
          (i) =>
            (!p.get('source') || i.source === p.get('source')) &&
            (!kw.length || i.matched_keywords.some((k) => kw.includes(k))) &&
            (!p.get('q') || i.title.replace(/\s/g, '').includes(p.get('q')!.replace(/\s/g, ''))) &&
            (!p.get('due') || i.due === p.get('due')),
        )
        return json({ keywords: KW, needs_keywords: false, total: items.length, min_budget: 100_000_000, items })
      }
    }
    const lastFeedUrl = (calls: { method: string; url: string }[]) => {
      const feed = calls.filter((c) => c.url.startsWith('/api/v1/feed'))
      return new URL(feed[feed.length - 1]!.url, 'http://x').searchParams
    }
    const titles = (w: VueWrapper) => w.findAll('li h3, li a').map((x) => x.text()).join('|')

    it('공고 종류와 맞은 키워드를 고르면 그것만 보이고, 주소에 남는다', async () => {
      const api = mockApi({ 'GET /api/v1/feed': feedRoute() })
      m = await mountAt('/')
      await m.wrapper.findAll('label').find((l) => l.text() === copy.bid.prespec)!.find('input').setValue(true)
      await settle()
      expect(lastFeedUrl(api.calls).get('source')).toBe('prespec')
      expect(m.router.currentRoute.value.query.source).toBe('prespec')
      expect(text(m.wrapper)).toContain('AI 플랫폼 운영 사전규격')
      expect(text(m.wrapper)).not.toContain('클라우드 전환 컨설팅')

      await m.wrapper.findAll('label').find((l) => l.text() === copy.feed.sourceAll)!.find('input').setValue(true)
      await settle()
      const chip = m.wrapper.findAll('button[data-kw]').find((b) => b.text() === '데이터')!
      expect(chip.attributes('aria-pressed')).toBe('false')
      await chip.trigger('click')
      await settle()
      expect(chip.attributes('aria-pressed')).toBe('true')
      expect(lastFeedUrl(api.calls).getAll('kw')).toEqual(['데이터'])
      expect(lastFeedUrl(api.calls).get('source')).toBeNull()
      expect(m.router.currentRoute.value.query.kw).toBe('데이터')
      expect(titles(m.wrapper)).toContain('공공 데이터 품질 관리')
      expect(titles(m.wrapper)).not.toContain('클라우드 전환 컨설팅')
      await chip.trigger('click')
      await settle()
      expect(lastFeedUrl(api.calls).getAll('kw')).toEqual([])
    })

    it('공고명으로 찾고, 맞는 게 없으면 안내와 [조건 지우기]', async () => {
      const api = mockApi({ 'GET /api/v1/feed': feedRoute() })
      m = await mountAt('/')
      await byLabel(m.wrapper, copy.feed.search).setValue('품질관리')
      await vi.waitFor(() => expect(lastFeedUrl(api.calls).get('q')).toBe('품질관리'))
      await settle()
      expect(m.router.currentRoute.value.query.q).toBe('품질관리')
      expect(text(m.wrapper)).toContain('공공 데이터 품질 관리')
      expect(text(m.wrapper)).not.toContain('클라우드 전환 컨설팅')

      await byLabel(m.wrapper, copy.feed.search).setValue('없는 사업')
      await vi.waitFor(() => expect(text(m!.wrapper)).toContain(copy.feed.emptyFiltered))
      const clear = m.wrapper.findAll('button').find((b) => b.text() === copy.feed.clearFilters)!
      await clear.trigger('click')
      await settle()
      expect(lastFeedUrl(api.calls).get('q')).toBeNull()
      expect(m.router.currentRoute.value.query).toEqual({})
      expect(text(m.wrapper)).toContain('클라우드 전환 컨설팅')
    })

    it('조건은 한 줄 조건 막대 하나에 모인다 (2026-11-18)', async () => {
      mockApi({ 'GET /api/v1/feed': feedRoute() })
      m = await mountAt('/')
      const bar = m.wrapper.get(`section[aria-label="${copy.feed.filters}"]`)
      expect(bar.find('input[name="feed-q"]').exists()).toBe(true)
      expect(bar.findAll('button[data-kw]')).toHaveLength(KW.length)
      expect(bar.get('[data-filter-end]').find('input[name="feed-small"]').exists()).toBe(true)
      // 공고명 칸 이름표는 화면에서 숨기고(자리 절약) 낭독기에는 남긴다
      expect(bar.findAll('label').find((l) => l.text() === copy.feed.search)!.classes()).toContain('sr-only')
    })

    it('기본은 마감 보드: 네 칸에 칸 건수, 공고는 제 칸에, 빈 칸은 안내 (2026-11-18)', async () => {
      mockApi({ 'GET /api/v1/feed': feedRoute() })
      m = await mountAt('/')
      const col = (d: string) => m!.wrapper.get(`section[data-due="${d}"]`)
      expect(['today', 'd3', 'd7', 'later'].map((d) => col(d).get('h2').text())).toEqual([
        copy.feed.due.today,
        copy.feed.due.d3,
        copy.feed.due.d7,
        copy.feed.due.later,
      ])
      expect(col('today').text()).toContain('클라우드 전환 컨설팅')
      expect(col('today').text()).toContain(copy.feed.total(1))
      expect(col('d3').text()).toContain('AI 플랫폼 운영 사전규격')
      expect(col('d7').text()).toContain(copy.feed.columnEmpty)
      expect(col('later').text()).toContain('공공 데이터 품질 관리')
      expect(text(m.wrapper)).toContain(copy.feed.total(3)) // 전체 = 칸 건수 합
      expect(m.wrapper.find('[data-more]').exists()).toBe(false)
    })

    it('칸의 [N건 더 보기]는 그 칸만 이어서 불러 붙인다', async () => {
      const many = Array.from({ length: 8 }, (_, i) => ({
        ...card({ bid_id: `b${200 + i}`, title: `사흘 안 공고 ${i}` }),
        matched_keywords: ['데이터'],
      }))
      const api = mockApi({
        'GET /api/v1/feed': (_: RequestInit, url: string) => {
          const p = new URL(url, 'http://x').searchParams
          const off = Number(p.get('offset'))
          const items = p.get('due') === 'd3' ? many.slice(off, off + Number(p.get('limit'))) : []
          return json({ keywords: KW, needs_keywords: false, total: p.get('due') === 'd3' ? 8 : 0, items })
        },
      })
      m = await mountAt('/')
      const d3 = () => m!.wrapper.get('section[data-due="d3"]')
      expect(d3().findAll('li')).toHaveLength(6)
      const more = d3().get('[data-more]')
      expect(more.text()).toBe(copy.feed.columnMore(2))
      await more.trigger('click')
      await settle()
      const last = new URL(api.calls[api.calls.length - 1]!.url, 'http://x').searchParams
      expect([last.get('due'), last.get('offset')]).toEqual(['d3', '6'])
      expect(d3().findAll('li')).toHaveLength(8)
      expect(d3().find('[data-more]').exists()).toBe(false)
    })

    it('[목록]으로 바꾸면 한 번에 부르는 예전 목록, 주소(view=list)에 남는다', async () => {
      const api = mockApi({ 'GET /api/v1/feed': feedRoute() })
      m = await mountAt('/')
      await m.wrapper.findAll('label').find((l) => l.text() === copy.feed.viewList)!.find('input').setValue(true)
      await settle()
      expect(m.router.currentRoute.value.query.view).toBe('list')
      expect(lastFeedUrl(api.calls).get('due')).toBeNull()
      expect(m.wrapper.find('section[data-due]').exists()).toBe(false)
      expect(titles(m.wrapper)).toContain('공공 데이터 품질 관리')

      m.wrapper.unmount()
      const again = mockApi({ 'GET /api/v1/feed': feedRoute() })
      m = await mountAt('/?view=list')
      expect(again.calls.filter((c) => c.url.startsWith('/api/v1/feed'))).toHaveLength(1)
      expect(m.wrapper.find('section[data-due]').exists()).toBe(false)
    })

    it('주소에 조건이 있으면 처음부터 그 조건으로 (상세에서 돌아왔을 때)', async () => {
      const api = mockApi({ 'GET /api/v1/feed': feedRoute() })
      m = await mountAt('/?source=regular&kw=클라우드&kw=모르는키워드&q=전환')
      const p = lastFeedUrl(api.calls)
      // 보드는 칸마다 한 번씩: 네 번 모두 같은 조건 + 칸(due)
      const feedCalls = api.calls.filter((c) => c.url.startsWith('/api/v1/feed'))
      expect(feedCalls.map((c) => new URL(c.url, 'http://x').searchParams.get('due'))).toEqual(['today', 'd3', 'd7', 'later'])
      expect([p.get('source'), p.getAll('kw').includes('클라우드'), p.get('q')]).toEqual(['regular', true, '전환'])
      // 내 키워드에 없는 값은 서버가 무시하고, 화면은 주소에서 지운다
      expect(m.router.currentRoute.value.query.kw).toBe('클라우드')
      expect((byLabel(m.wrapper, copy.feed.search).element as HTMLInputElement).value).toBe('전환')
      expect(m.wrapper.findAll('button[data-kw]').find((b) => b.text() === '클라우드')!.attributes('aria-pressed')).toBe(
        'true',
      )
    })
  })

  it('키워드가 3개 미만이면 키워드 설정으로 보낸다', async () => {
    mockApi({
      'GET /api/v1/feed': json({ keywords: ['AI'], needs_keywords: true, total: 0, items: [] }),
      'GET /api/v1/profiles': json({ items: [] }),
      'GET /api/v1/teams/me': json(NO_TEAM),
    })
    m = await mountAt('/')
    // 지연 로딩되는 화면으로 replace: 고정 대기 대신 조건이 될 때까지 기다린다
    await vi.waitFor(() => expect(m!.router.currentRoute.value.path).toBe('/onboarding'), { timeout: 5000 })
  })

  it('로그인한 사람이 로그인 화면에 오면 홈으로', async () => {
    mockApi({ 'GET /api/v1/feed': json({ keywords: [], needs_keywords: true, total: 0, items: [] }) })
    m = await mountAt('/login')
    expect(['/', '/onboarding']).toContain(m.router.currentRoute.value.path)
  })
})

describe('키워드 설정 (/onboarding)', () => {
  it('팀 키워드는 보여 주기만 하고, 합쳐 3개가 되어야 저장된다', async () => {
    const api = mockApi({
      'GET /api/v1/profiles': json({ items: [profile({ scope: 'team', keywords: ['클라우드'] })] }),
      'GET /api/v1/teams/me': json(myTeam('member')),
      'PATCH /api/v1/me': json({ ...MEMBER, interest_keywords: ['AI', '데이터'] }),
      'GET /api/v1/feed': json({ keywords: [], needs_keywords: false, total: 0, items: [] }),
    })
    m = await mountAt('/onboarding')
    expect(text(m.wrapper)).toContain('클라우드')
    const save = () => m!.wrapper.findAll('button').find((b) => b.text() === copy.onboarding.save)!
    expect(save().attributes('disabled')).toBeDefined()
    const input = byLabel(m.wrapper, copy.onboarding.personalLabel)
    for (const k of ['AI', '데이터']) {
      await input.setValue(k)
      await input.trigger('keydown', { key: 'Enter' })
    }
    expect(save().attributes('disabled')).toBeUndefined()
    await save().trigger('click')
    await vi.waitFor(() => expect(m!.router.currentRoute.value.path).toBe('/'), { timeout: 5000 })
    expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ interest_keywords: ['AI', '데이터'] })
  })
})

describe('초대 수락 (/join)', () => {
  it('코드로 팀에 들어가 팀 설정으로 간다', async () => {
    const api = mockApi({
      'GET /api/v1/teams/me': () => json(NO_TEAM),
      'POST /api/v1/teams/join': json(myTeam('member')),
    })
    m = await mountAt('/join?code=ABCD234567')
    expect(text(m.wrapper)).toContain('ABCD234567')
    await m.wrapper.findAll('button').find((b) => b.text() === copy.team.joinSubmit)!.trigger('click')
    await vi.waitFor(() => expect(m!.router.currentRoute.value.path).toBe('/settings/team'), { timeout: 5000 })
    expect(api.calls.find((c) => c.url.endsWith('/teams/join'))?.body).toEqual({ code: 'ABCD234567' })
  })

  it('이미 팀이 있으면 안내만', async () => {
    mockApi({ 'GET /api/v1/teams/me': json(myTeam('member')) })
    m = await mountAt('/join?code=ZZZZ234567')
    expect(text(m.wrapper)).toContain(copy.team.alreadyInTeam)
  })
})

describe('팀 설정 (/settings/team)', () => {
  it('팀이 없으면 만들기와 코드로 들어가기', async () => {
    const api = mockApi({
      'GET /api/v1/teams/me': json(NO_TEAM),
      'POST /api/v1/teams': json(myTeam('owner'), 201),
    })
    m = await mountAt('/settings/team')
    await byLabel(m.wrapper, copy.team.nameLabel).setValue('AI 플랫폼팀')
    await m.wrapper.findAll('button').find((b) => b.text() === copy.team.create)!.trigger('click')
    await settle()
    expect(api.calls.find((c) => c.method === 'POST' && c.url.endsWith('/teams'))?.body).toEqual({ name: 'AI 플랫폼팀' })
    expect(text(m.wrapper)).toContain(copy.team.inviteLink)
  })

  it('팀장은 초대 링크·재발급·내보내기, 팀원은 링크와 나가기만', async () => {
    mockApi({ 'GET /api/v1/teams/me': json(myTeam('owner')) })
    m = await mountAt('/settings/team')
    const owner = text(m.wrapper)
    expect(owner).toContain('/join?code=ABCD234567')
    expect(owner).toContain(copy.team.rotate)
    expect(m.wrapper.findAll(`button[aria-label="${copy.team.remove('비')}"]`)).toHaveLength(1)
    m.wrapper.unmount()

    mockApi({ 'GET /api/v1/teams/me': json(myTeam('member')) })
    m = await mountAt('/settings/team')
    const mate = text(m.wrapper)
    expect(mate).toContain('/join?code=ABCD234567')
    expect(mate).not.toContain(copy.team.rotate)
    expect(m.wrapper.findAll(`button[aria-label="${copy.team.remove('에이')}"]`)).toHaveLength(0)
    expect(mate).toContain(copy.team.leave)
  })
})

describe('팀 분석 공유', () => {
  it('내 분석이 없고 팀원 분석이 있으면 팀 분석을 보여 준다', async () => {
    mockApi({
      'GET /api/v1/bids/b101': json({
        ...card(),
        prespec_reg_no: null,
        related_bid_id: null,
        files: [],
        summary: null,
        my_analysis_id: null,
        team_analysis_id: 55,
      }),
      'GET /api/v1/profiles': json({ items: [profile()] }),
      'GET /api/v1/analyses/55': json({
        analysis_id: 55,
        bid_id: 'b101',
        profile_id: 9,
        markdown: '',
        created_at: '2026-11-10T00:00:00Z',
        analysis: {
          overview: '팀원이 만든 개요',
          requirements: [],
          evaluation: { method: null, items: [] },
          schedule: [],
          budget_contract: { budget_text: null, contract_method: null, payment_terms: null, period: null },
          risks: [],
          fit: { score: 70, verdict: 'possible', strengths: [], gaps: [], reasoning: '' },
          next_actions: [],
          warnings: [],
        },
      }),
    })
    m = await mountAt('/bids/b101')
    await settle()
    const t = text(m.wrapper)
    expect(t).toContain('팀원이 만든 개요')
    expect(t).toContain(copy.detail.teamAnalysis)
  })

  it('팀원 분석의 프로필 보완 안내에는 내 프로필 고치기 링크를 두지 않는다', async () => {
    mockApi({
      'GET /api/v1/bids/b101': json({
        ...card(),
        prespec_reg_no: null,
        related_bid_id: null,
        files: [],
        summary: null,
        my_analysis_id: null,
        team_analysis_id: 56,
      }),
      'GET /api/v1/profiles': json({ items: [profile()] }),
      'GET /api/v1/analyses/56': json({
        analysis_id: 56,
        bid_id: 'b101',
        profile_id: 9,
        markdown: '',
        created_at: '2026-11-10T00:00:00Z',
        analysis: {
          understanding: { purpose: '팀원 분석', scope: [], conditions: [] },
          fit: { score: 70, verdict: 'possible', reasoning: '' },
          team_needs: { have: [], need: [] },
          profile_missing: ['PM 자격'],
          risks: [],
          next_actions: [],
          warnings: [],
          profile_brief: true,
        },
      }),
    })
    m = await mountAt('/bids/b101')
    await settle()
    const note = m.wrapper.get('[data-test="profile-notice"]')
    expect(note.text()).toContain(copy.analysis.profileNotice)
    expect(note.find('a').exists()).toBe(false)
  })

  it('내 기록에서 팀 분석을 따로 본다', async () => {
    const api = mockApi({
      'GET /api/v1/analyses': (_init, url) =>
        json({ items: [], total: 0, ...(url.includes('scope=team') ? {} : {}) }),
      'GET /api/v1/search-runs': json({ items: [], total: 0 }),
      'GET /api/v1/bookmarks': json({ items: [] }),
      'GET /api/v1/teams/me': json(myTeam('member')),
    })
    m = await mountAt('/library?tab=analyses')
    await m.wrapper.findAll('button').find((b) => b.text() === copy.library.teamAnalyses)!.trigger('click')
    await settle()
    expect(api.calls.some((c) => c.url.includes('/analyses?') && c.url.includes('scope=team'))).toBe(true)
  })
})

describe('프로필의 개인·팀 구분', () => {
  it('팀이 있으면 팀 프로필로 만들 수 있고 목록에 팀 배지', async () => {
    const api = mockApi({
      'GET /api/v1/profiles': json({ items: [profile({ scope: 'team', name: '팀 공용' })] }),
      'GET /api/v1/teams/me': json(myTeam('member')),
      'POST /api/v1/profiles': json(profile({ id: 8, scope: 'team' }), 201),
    })
    m = await mountAt('/settings/profiles')
    expect(text(m.wrapper)).toContain(copy.profile.teamBadge)
    await m.wrapper.findAll('button').find((b) => b.text() === copy.profile.newProfile)!.trigger('click')
    await settle()
    const scope = m.wrapper.find(`[data-scope-select]`)
    expect(scope.exists()).toBe(true)
    void api
  })
})

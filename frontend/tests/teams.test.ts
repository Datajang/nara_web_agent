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

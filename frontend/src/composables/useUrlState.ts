// 검색 조건 ↔ URL 쿼리 (SPEC §7.3 URL 동기화, §7.11-4). 조건에 개인정보가 없어 공유해도 안전하다.
import type { LocationQuery, LocationQueryRaw } from 'vue-router'
import type { SearchQuery } from '@/api/types'

export type Match = 'all' | 'any'
export type Source = 'all' | 'regular' | 'prespec'
export type Status = 'open' | 'all'
export type Sort = 'notice_desc' | 'deadline_asc' | 'budget_desc'
export type Period = 7 | 14 | 30 | 60 | 90 | 'custom'

export interface SearchState {
  keywords: string[]
  match: Match
  source: Source
  period: Period
  from: string
  to: string
  status: Status
  budgetMin: string // 만원
  budgetMax: string
  org: string
  sort: Sort
  view: 'cards' | 'table'
}

export const PERIODS = [7, 14, 30, 60, 90] as const
export const PAGE = 50

export function defaultState(): SearchState {
  return {
    keywords: [],
    match: 'all',
    source: 'all',
    period: 14,
    from: '',
    to: '',
    status: 'open',
    budgetMin: '',
    budgetMax: '',
    org: '',
    sort: 'notice_desc',
    view: 'cards',
  }
}

const one = (v: LocationQuery[string] | undefined) => (Array.isArray(v) ? v[0] : v) ?? ''
function pick<T extends string>(v: string, allowed: readonly T[], dflt: T): T {
  return (allowed as readonly string[]).includes(v) ? (v as T) : dflt
}

export function parseSearch(q: LocationQuery): SearchState {
  const s = defaultState()
  const kw = one(q.q)
  s.keywords = kw ? [...new Set(kw.split(',').map((k) => k.trim()).filter(Boolean))].slice(0, 10) : []
  s.match = pick(one(q.match), ['all', 'any'], 'all')
  s.source = pick(one(q.source), ['all', 'regular', 'prespec'], 'all')
  s.status = pick(one(q.status), ['open', 'all'], 'open')
  s.sort = pick(one(q.sort), ['notice_desc', 'deadline_asc', 'budget_desc'], 'notice_desc')
  s.view = pick(one(q.view), ['cards', 'table'], 'cards')
  const from = one(q.from)
  const to = one(q.to)
  const days = Number(one(q.days))
  if (from && to) {
    s.period = 'custom'
    s.from = from
    s.to = to
  } else if ((PERIODS as readonly number[]).includes(days)) {
    s.period = days as Period
  }
  s.budgetMin = one(q.bmin).replace(/\D/g, '')
  s.budgetMax = one(q.bmax).replace(/\D/g, '')
  s.org = one(q.org).slice(0, 100)
  return s
}

/** 기본값과 같은 항목은 URL에 쓰지 않는다. */
export function toQuery(s: SearchState): LocationQueryRaw {
  const d = defaultState()
  const q: LocationQueryRaw = {}
  if (s.keywords.length) q.q = s.keywords.join(',')
  if (s.match !== d.match) q.match = s.match
  if (s.source !== d.source) q.source = s.source
  if (s.period === 'custom' && s.from && s.to) {
    q.from = s.from
    q.to = s.to
  } else if (s.period !== 'custom' && s.period !== d.period) q.days = String(s.period)
  if (s.status !== d.status) q.status = s.status
  if (s.budgetMin) q.bmin = s.budgetMin
  if (s.budgetMax) q.bmax = s.budgetMax
  if (s.org.trim()) q.org = s.org.trim()
  if (s.sort !== d.sort) q.sort = s.sort
  if (s.view !== d.view) q.view = s.view
  return q
}

export function toRequest(s: SearchState): Partial<SearchQuery> {
  const body: Partial<SearchQuery> = {
    keywords: s.keywords,
    match: s.match,
    source: s.source,
    status: s.status,
    sort: s.sort,
    limit: PAGE,
  }
  if (s.period === 'custom' && s.from && s.to) {
    body.from = s.from
    body.to = s.to
  } else {
    body.days = s.period === 'custom' ? 14 : s.period
  }
  if (s.budgetMin) body.budget_min = Number(s.budgetMin) * 10_000
  if (s.budgetMax) body.budget_max = Number(s.budgetMax) * 10_000
  if (s.org.trim()) body.org = s.org.trim()
  return body
}

/** 저장된 검색 조건(search_runs.query)에서 화면 조건을 만든다. */
export function fromRunQuery(query: Record<string, unknown>): SearchState {
  const s = defaultState()
  const kw = query.keywords
  if (Array.isArray(kw)) s.keywords = kw.map(String)
  if (query.match === 'any') s.match = 'any'
  if (query.source === 'regular' || query.source === 'prespec') s.source = query.source
  if (query.status === 'all') s.status = 'all'
  if (typeof query.sort === 'string') s.sort = pick(query.sort, ['notice_desc', 'deadline_asc', 'budget_desc'], 'notice_desc')
  if (typeof query.from === 'string' && typeof query.to === 'string') {
    s.period = 'custom'
    s.from = query.from
    s.to = query.to
  } else if ((PERIODS as readonly number[]).includes(Number(query.days))) {
    s.period = Number(query.days) as Period
  }
  if (typeof query.budget_min === 'number') s.budgetMin = String(Math.round(query.budget_min / 10_000))
  if (typeof query.budget_max === 'number') s.budgetMax = String(Math.round(query.budget_max / 10_000))
  if (typeof query.org === 'string') s.org = query.org
  return s
}

// 낙찰·회사 설정·업체 검색 API (SPEC §15.6, P9).
import { api } from './client'
import type { components } from './schema'

type S = components['schemas']
export type CompanyStatus = S['CompanyOut']
export type CompanySettingsIn = S['CompanySettingsIn']
export type Lookup = S['CompanyLookupOut']
export type AwardSummary = S['AwardSummaryOut']
export type AwardList = S['AwardListOut']
export type Award = S['AwardOut']
export type AwardPeriod = S['PeriodOut']
export type CompanyHit = S['CompanyHitOut']

export interface AwardQuery {
  bizno?: string // 비우면 우리 회사
  field?: string
  org?: string
  cursor?: string | null
  limit?: number
}

function qs(params: Record<string, string | number | null | undefined>): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const awardsApi = {
  company: () => api.get<CompanyStatus>('/company'),
  lookup: (bizno: string) => api.post<Lookup>('/admin/company/lookup', { bizno } satisfies S['BiznoIn']),
  saveCompany: (body: CompanySettingsIn) => api.put<CompanyStatus>('/admin/company', body),
  summary: (bizno?: string) => api.get<AwardSummary>(`/awards/summary${qs({ bizno })}`),
  list: (q: AwardQuery = {}) =>
    api.get<AwardList>(
      `/awards${qs({ bizno: q.bizno, field: q.field, org: q.org, cursor: q.cursor, limit: q.limit })}`,
    ),
  search: (q: string) => api.get<S['CompanySearchOut']>(`/companies/search${qs({ q })}`),
  companySummary: (bizno: string) => api.get<AwardSummary>(`/companies/${encodeURIComponent(bizno)}`),
}

/** 사업자번호: 숫자만 남겨 10자리면 그 값, 아니면 null. */
export function normalizeBizno(v: string): string | null {
  const d = v.replace(/\D/g, '')
  return d.length === 10 ? d : null
}

/** 123-45-67890 형식으로. */
export function formatBizno(b: string): string {
  return b.length === 10 ? `${b.slice(0, 3)}-${b.slice(3, 5)}-${b.slice(5)}` : b
}

/** 분야 키워드 사전 ↔ 편집용 글(한 줄 "분야: 키워드, 키워드"). */
export function keywordsToText(k: Record<string, string[]>): string {
  return Object.entries(k)
    .map(([tag, words]) => `${tag}: ${words.join(', ')}`)
    .join('\n')
}

export function parseKeywords(text: string): { value: Record<string, string[]> } | { errorLine: number } {
  const value: Record<string, string[]> = {}
  const lines = text.split('\n')
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]!.trim()
    if (!line) continue
    const at = line.indexOf(':')
    const tag = at > 0 ? line.slice(0, at).trim() : ''
    const words = at > 0 ? line.slice(at + 1).split(',').map((w) => w.trim()).filter(Boolean) : []
    if (!tag || !words.length || tag.length > 30 || words.some((w) => w.length > 30)) return { errorLine: i + 1 }
    value[tag] = [...new Set([...(value[tag] ?? []), ...words])].slice(0, 20)
  }
  return { value }
}

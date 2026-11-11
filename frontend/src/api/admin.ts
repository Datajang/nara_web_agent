// 관리자 사용량·수집기 API (SPEC §6.2, §7.9).
import { api } from './client'
import type { CollectorRunIn, CollectorRunList, UsageRow } from './types'

export const opsApi = {
  usage: (from?: string, to?: string) => {
    const q = new URLSearchParams({ group: 'day' })
    if (from) q.set('from', from)
    if (to) q.set('to', to)
    return api.get<{ items: UsageRow[] }>(`/admin/usage?${q}`)
  },
  collectorRuns: (limit = 20) => api.get<CollectorRunList>(`/admin/collector/runs?limit=${limit}`),
  runCollector: (body: CollectorRunIn) => api.post<{ status: string }>('/admin/collector/run', body),
}

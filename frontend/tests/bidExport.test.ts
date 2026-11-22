// 입찰공고 목록 다운로드 (2026-11-22): 화면에 보이는 공고 ID를 순서대로 보내고, 오늘(KST) 날짜 파일 이름으로 저장.
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ExportButton from '@/components/bid/ExportButton.vue'
import { copy } from '@/copy'
import { exportFilename } from '@/utils/exportFilename'
import { mockApi, settle } from './helpers'

const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('입찰공고 목록 다운로드', () => {
  it('파일 이름은 한국 날짜 기준', () => {
    expect(exportFilename(new Date('2026-11-22T16:00:00Z'))).toBe('2026-11-23_입찰공고 목록.xlsx')
  })

  it('보이는 공고 ID를 순서대로 보내고 받은 파일을 저장한다', async () => {
    const api = mockApi({
      'POST /api/v1/bids/export': () => new Response('x', { status: 200, headers: { 'content-type': XLSX } }),
    })
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} }))
    const names: string[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      names.push(this.download)
    })
    const w = mount(ExportButton, { props: { bidIds: ['b3', 'b1'] } })
    const btn = w.get('button')
    expect(btn.text()).toContain(copy.exportList.button)
    await btn.trigger('click')
    await settle()
    const call = api.calls.find((c) => c.method === 'POST')!
    expect(call.body).toEqual({ bid_ids: ['b3', 'b1'] })
    expect(names).toEqual([exportFilename(new Date())])
  })

  it('보이는 공고가 없으면 누를 수 없다', () => {
    const w = mount(ExportButton, { props: { bidIds: [] } })
    expect(w.get('button').attributes('disabled')).toBeDefined()
  })
})

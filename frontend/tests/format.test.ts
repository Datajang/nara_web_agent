// §10.10-2: 포맷 규칙 예시와 시간대 경계.
import { describe, expect, it } from 'vitest'
import { formatDataAsOf, formatDateTime, formatDday, formatMoney } from '@/utils/format'

describe('formatMoney', () => {
  it.each([
    [null, '미공개'],
    [0, '미공개'],
    [8500, '8,500원'],
    [85000, '8.5만'],
    [45000000, '4,500만'],
    [120000000, '1.2억'],
    [250000000, '2.5억'],
    [1500000000, '15억'],
    [100000000, '1억'],
  ])('%s → %s', (v, out) => {
    expect(formatMoney(v)).toBe(out)
  })
})

describe('formatDday (KST 기준)', () => {
  // now = 2026-11-10 15:00 KST (06:00Z)
  const now = new Date('2026-11-10T06:00:00Z')
  it.each([
    ['2026-11-13T01:00:00Z', 'D-3'], // 11-13 10:00 KST
    ['2026-11-10T09:00:00Z', 'D-day'], // 오늘 18:00 KST, 아직 전
    ['2026-11-10T05:00:00Z', '마감'], // 오늘 14:00 KST, 지남
    [null, '마감 미정'],
  ])('%s → %s', (deadline, out) => {
    expect(formatDday(deadline, now)).toBe(out)
  })

  it('UTC로는 같은 날이지만 KST로는 다음 날이면 D-1', () => {
    // now 2026-11-10 23:30 KST(14:30Z), 마감 2026-11-11 00:30 KST(15:30Z) — UTC로는 둘 다 11-10
    expect(formatDday('2026-11-10T15:30:00Z', new Date('2026-11-10T14:30:00Z'))).toBe('D-1')
  })

  it('KST 자정 직전 마감은 당일 D-day', () => {
    expect(formatDday('2026-11-10T14:59:00Z', new Date('2026-11-10T00:00:00Z'))).toBe('D-day')
  })
})

describe('날짜 표시', () => {
  it('formatDateTime: UTC ISO → KST', () => {
    expect(formatDateTime('2026-11-20T01:00:00Z')).toBe('2026-11-20 10:00')
    expect(formatDateTime('2026-11-20T16:05:00Z')).toBe('2026-11-21 01:05')
  })
  it('formatDataAsOf: UTC ISO → MM-DD HH:mm KST', () => {
    expect(formatDataAsOf('2026-11-09T01:20:00Z')).toBe('11-09 10:20')
  })
})

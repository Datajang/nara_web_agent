// 포맷 규칙 (SPEC §10.5). 날짜는 항상 KST로 표시한다.
import { copy } from '@/copy'

const KST_OFFSET_MS = 9 * 60 * 60 * 1000

function trimDecimal(n: number): string {
  const s = n.toFixed(1)
  return s.endsWith('.0') ? s.slice(0, -2) : s
}

function withCommas(s: string): string {
  const [int = '', frac] = s.split('.')
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return frac ? `${grouped}.${frac}` : grouped
}

export function formatMoney(value: number | null | undefined): string {
  if (!value) return copy.format.undisclosed
  if (value >= 100_000_000) return `${withCommas(trimDecimal(value / 100_000_000))}${copy.format.eok}`
  if (value >= 10_000) return `${withCommas(trimDecimal(value / 10_000))}${copy.format.man}`
  return `${withCommas(String(value))}${copy.format.won}`
}

function kstParts(d: Date) {
  const k = new Date(d.getTime() + KST_OFFSET_MS)
  return {
    y: k.getUTCFullYear(),
    m: k.getUTCMonth() + 1,
    d: k.getUTCDate(),
    hh: k.getUTCHours(),
    mm: k.getUTCMinutes(),
  }
}

function kstDayNumber(d: Date): number {
  return Math.floor((d.getTime() + KST_OFFSET_MS) / 86_400_000)
}

const pad = (n: number) => String(n).padStart(2, '0')

export function formatDday(deadlineIso: string | null | undefined, now: Date = new Date()): string {
  if (!deadlineIso) return copy.format.noDeadline
  const deadline = new Date(deadlineIso)
  if (deadline.getTime() <= now.getTime()) return copy.format.closed
  const days = kstDayNumber(deadline) - kstDayNumber(now)
  return days === 0 ? 'D-day' : `D-${days}`
}

export function formatDateTime(iso: string): string {
  const p = kstParts(new Date(iso))
  return `${p.y}-${pad(p.m)}-${pad(p.d)} ${pad(p.hh)}:${pad(p.mm)}`
}

export function formatDataAsOf(iso: string): string {
  const p = kstParts(new Date(iso))
  return `${pad(p.m)}-${pad(p.d)} ${pad(p.hh)}:${pad(p.mm)}`
}

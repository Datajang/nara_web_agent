// §10.10-1: 토큰 색 조합 대비가 임계값(텍스트 4.5, 입력 테두리 3.0)을 넘는다.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const css = readFileSync(resolve(process.cwd(), 'src/styles/tokens.css'), 'utf8')

function token(name: string): string {
  const m = css.match(new RegExp(`--${name}\\s*:\\s*(#[0-9a-fA-F]{6})\\s*;`))
  if (!m?.[1]) throw new Error(`토큰 없음: --${name}`)
  return m[1]
}

function luminance(hex: string): number {
  const ch = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  const [r, g, b] = ch.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)) as [
    number,
    number,
    number,
  ]
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number]
  return (hi + 0.05) / (lo + 0.05)
}

const WHITE = '#FFFFFF'
const TEXT: Array<[string, string]> = [
  ['text', 'surface'],
  ['text', 'bg'],
  ['text-2', 'surface'],
  ['text-2', 'surface-2'],
  ['text-3', 'surface'],
  ['text-3', 'bg'],
  ['primary-hover', 'primary-soft'],
  ['success-fg', 'success-bg'],
  ['warning-fg', 'warning-bg'],
  ['danger-fg', 'danger-bg'],
  ['neutral-fg', 'neutral-bg'],
]
const ON_WHITE_TEXT = ['primary', 'primary-hover', 'danger-fg'] // 흰 글자를 올리는 배경

describe('색상 토큰 대비 (§10.1)', () => {
  it('표면은 흰색이다', () => {
    expect(token('surface').toUpperCase()).toBe(WHITE)
  })

  it.each(TEXT)('--%s / --%s ≥ 4.5', (fg, bg) => {
    expect(contrast(token(fg), token(bg))).toBeGreaterThanOrEqual(4.5)
  })

  it.each(ON_WHITE_TEXT)('흰색 / --%s ≥ 4.5', (bg) => {
    expect(contrast(WHITE, token(bg))).toBeGreaterThanOrEqual(4.5)
  })

  it.each(['surface', 'bg'])('--border-input / --%s ≥ 3.0 (비텍스트)', (bg) => {
    expect(contrast(token('border-input'), token(bg))).toBeGreaterThanOrEqual(3.0)
  })
})

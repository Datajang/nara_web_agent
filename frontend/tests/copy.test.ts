// §10.10-8: 화면 문구는 copy.ts에만 둔다. 컴포넌트·화면 코드에 한글 문자열이 있으면 실패.
// 주석(한국어 허용, 규칙 9)은 지우고 검사한다.
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = resolve(process.cwd(), 'src')
const ALLOWED = new Set(['copy.ts'])
const HANGUL = /[ㄱ-ㆎ가-힣]/

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) return files(p)
    return /\.(vue|ts)$/.test(name) && !name.endsWith('.d.ts') ? [p] : []
  })
}

export function stripComments(code: string): string {
  return code
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:'"`])\/\/.*$/gm, '$1')
}

describe('문구 하드코딩 검사', () => {
  it('src 아래에 copy.ts 외 한글 문자열이 없다', () => {
    const offenders = files(SRC)
      .filter((p) => !ALLOWED.has(relative(SRC, p)))
      .flatMap((p) =>
        stripComments(readFileSync(p, 'utf8'))
          .split('\n')
          .map((line, i) => [line, i] as const)
          .filter(([line]) => HANGUL.test(line))
          .map(([line, i]) => `${relative(SRC, p)}:${i + 1}: ${line.trim()}`),
      )
    expect(offenders).toEqual([])
  })

  it('주석 제거기는 URL을 지우지 않는다', () => {
    expect(stripComments("const u = 'https://x.y' // 주석")).toContain('https://x.y')
    expect(stripComments('<!-- 주석 --><p>a</p>')).toBe('<p>a</p>')
  })
})

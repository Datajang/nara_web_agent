// §10.10-3: v-html은 MarkdownView 외에서 ESLint 오류.
import { ESLint } from 'eslint'
import { describe, expect, it } from 'vitest'

const cwd = process.cwd()
const SFC = '<template><div v-html="html" /></template>\n<script setup lang="ts">\nconst html = "<b>x</b>"\n</script>\n'

async function lint(path: string) {
  const eslint = new ESLint({ cwd })
  const [result] = await eslint.lintText(SFC, { filePath: path })
  return result?.messages.filter((m) => m.ruleId === 'vue/no-v-html') ?? []
}

describe('ESLint vue/no-v-html', () => {
  it('일반 컴포넌트에서는 오류', async () => {
    const msgs = await lint('src/components/bid/BidCard.vue')
    expect(msgs).toHaveLength(1)
    expect(msgs[0]?.severity).toBe(2)
  })

  it('MarkdownView만 예외', async () => {
    expect(await lint('src/components/ui/MarkdownView.vue')).toHaveLength(0)
  })
}, 30_000)

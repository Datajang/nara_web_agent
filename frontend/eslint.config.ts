import { globalIgnores } from 'eslint/config'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import pluginVue from 'eslint-plugin-vue'
import pluginVitest from '@vitest/eslint-plugin'

export default defineConfigWithVueTs(
  {
    name: 'app/files-to-lint',
    files: ['**/*.{vue,ts,mts,tsx}'],
  },

  globalIgnores(['**/dist/**', '**/dist-ssr/**', '**/coverage/**', 'src/api/schema.d.ts']),

  ...pluginVue.configs['flat/essential'],
  vueTsConfigs.recommended,

  // XSS: v-html 금지 (SPEC §9.5, §10.10-3). 마크다운은 DOMPurify를 거치는 MarkdownView 한 곳만 예외.
  {
    name: 'app/no-v-html',
    rules: { 'vue/no-v-html': 'error' },
  },
  {
    name: 'app/markdown-view-exception',
    files: ['src/components/ui/MarkdownView.vue'],
    rules: { 'vue/no-v-html': 'off' },
  },

  {
    ...pluginVitest.configs.recommended,
    files: ['tests/**/*'],
  },
)

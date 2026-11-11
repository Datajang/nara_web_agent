// E2E 스모크 (SPEC §12.8 main 병합 게이트). 가짜 LLM 백엔드 + vite preview를 먼저 띄운다.
// 로컬: E2E_BASE=http://localhost:4173 E2E_ADMIN=... E2E_ADMIN_PW=... npx playwright test
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: 'e2e',
  testMatch: '*.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0, // 불안정하면 재시도로 덮지 않고 원인을 고친다 (§12.9)
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  timeout: 60_000,
  use: {
    baseURL: process.env.E2E_BASE ?? 'http://localhost:4173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})

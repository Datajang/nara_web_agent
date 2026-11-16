import { chromium } from 'playwright'
const OUT = process.env.OUT
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
await page.goto('http://127.0.0.1:5173/login')
await page.getByLabel('이메일').fill('ui-check@example.com')
await page.getByLabel('비밀번호').fill(process.env.PW)
await page.getByRole('button', { name: '로그인' }).click()
await page.waitForURL((u) => u.pathname !== '/login')
await page.goto('http://127.0.0.1:5173/bids/b568')
await page.getByRole('button', { name: '분석하기' }).click()
const t0 = Date.now()
const bar = page.getByRole('progressbar')
await bar.waitFor({ timeout: 60000 })
const log = []
for (let i = 0; i < 60; i++) {
  if (!(await bar.count())) break
  const v = await bar.getAttribute('aria-valuenow')
  const txt = (await bar.locator('xpath=..').innerText()).replace(/\n/g, ' | ')
  log.push(`${Math.round((Date.now() - t0) / 1000)}s ${v}% ${txt}`)
  if (i === 2 || i === 8 || i === 20) await bar.locator('xpath=../..').screenshot({ path: `${OUT}/bar-${i}.png` })
  await page.waitForTimeout(10000)
}
console.log(log.join('\n'))
await page.screenshot({ path: `${OUT}/bar-done.png`, fullPage: false })
await browser.close()

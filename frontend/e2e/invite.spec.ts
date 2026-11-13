// P6 초대 수락 (SPEC §13 P6): 팀장이 초대 링크를 만들고, 로그인 전인 회원이 링크로 와서 로그인하면
// 초대 화면으로 돌아와 팀에 들어간다. 끝에 회원이 나가 다시 돌려도 같은 결과가 난다.
// 데이터: backend `python -m scripts.seed_e2e`(E2E_MEMBER·E2E_MEMBER_PW로 팀 없는 회원 1명).
import { expect, test, type Page } from '@playwright/test'
import { copy } from '../src/copy'

const ADMIN = process.env.E2E_ADMIN ?? 'e2e-admin@corp.example'
const ADMIN_PW = process.env.E2E_ADMIN_PW ?? 'e2e-admin-password-1'
const MEMBER = process.env.E2E_MEMBER ?? 'e2e-member@corp.example'
const MEMBER_PW = process.env.E2E_MEMBER_PW ?? 'e2e-member-password-1'

async function login(page: Page, email: string, password: string) {
  await page.getByLabel('이메일').fill(email)
  await page.getByLabel('비밀번호').fill(password)
  await page.getByRole('button', { name: '로그인' }).click()
}

test('초대 링크 → 로그인 → 팀에 들어가기 → 나가기', async ({ browser }) => {
  // 팀장: 팀이 없으면 만들고 초대 링크를 읽는다
  const ownerCtx = await browser.newContext()
  const owner = await ownerCtx.newPage()
  await owner.goto('/login')
  await login(owner, ADMIN, ADMIN_PW)
  await owner.waitForURL((u) => u.pathname !== '/login')
  await owner.goto('/settings/team')
  const createBtn = owner.getByRole('button', { name: copy.team.create })
  const invite = owner.getByText(copy.team.inviteLink, { exact: true })
  await expect(createBtn.or(invite)).toBeVisible()
  if (await createBtn.isVisible()) {
    await owner.getByLabel(copy.team.nameLabel).fill('E2E 팀')
    await createBtn.click()
  }
  await expect(invite).toBeVisible()
  const link = (await owner.locator('code').filter({ hasText: '/join?code=' }).textContent())!.trim()
  const { pathname, search } = new URL(link)

  // 회원: 로그인 전에 링크를 열면 로그인 뒤 초대 화면으로 돌아온다
  const memberCtx = await browser.newContext()
  const member = await memberCtx.newPage()
  await member.goto(pathname + search)
  await member.waitForURL(/\/login/)
  await login(member, MEMBER, MEMBER_PW)
  await member.waitForURL((u) => u.pathname === '/join')
  await member.getByRole('button', { name: copy.team.joinSubmit }).click()
  await member.waitForURL((u) => u.pathname === '/settings/team')
  await expect(member.getByText(copy.team.leave)).toBeVisible()
  await expect(member.getByRole('button', { name: copy.team.rotate })).toHaveCount(0) // 팀원은 재발급 못 함

  // 팀장 화면에도 새 팀원이 보인다
  await owner.reload()
  await expect(owner.getByText(MEMBER.split('@')[0], { exact: true })).toBeVisible()

  // 회원이 나가면 다시 팀 만들기·코드 입력 화면
  await member.getByRole('button', { name: copy.team.leave }).click()
  await member.getByRole('button', { name: copy.common.confirm }).click()
  await expect(member.getByRole('button', { name: copy.team.create })).toBeVisible()

  await ownerCtx.close()
  await memberCtx.close()
})

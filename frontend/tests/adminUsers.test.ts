// §7.9 사용자 관리: 활성 계정의 소속 팀·팀장 표시 (2026-11-25 사용자 요청)
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { copy } from '@/copy'
import { ADMIN, json, mockApi, mountAt, settle, type Mounted } from './helpers'

let m: Mounted | null = null
beforeEach(() => {
  document.body.innerHTML = ''
})
afterEach(() => {
  m?.wrapper.unmount()
  m = null
  vi.unstubAllGlobals()
})

const user = (id: number, email: string, extra: Record<string, unknown> = {}) => ({
  id,
  email,
  display_name: email.split('@')[0],
  role: 'member',
  status: 'active',
  email_verified_at: '2026-11-20T00:00:00Z',
  last_login_at: null,
  created_at: '2026-11-20T00:00:00Z',
  team: null,
  team_role: null,
  ...extra,
})

describe('UsersView', () => {
  it('활성 탭에서 소속 팀과 팀장 표시, 소속 없으면 그렇게 표시', async () => {
    mockApi(
      {
        'GET /api/v1/admin/users': json({
          items: [
            user(1, 'lead@corp.example', { team: { id: 2, name: 'AX컨설팅2팀' }, team_role: 'owner' }),
            user(2, 'mem@corp.example', { team: { id: 2, name: 'AX컨설팅2팀' }, team_role: 'member' }),
            user(3, 'solo@corp.example'),
          ],
          total: 3,
        }),
      },
      ADMIN,
    )
    m = await mountAt('/admin/users?tab=active')
    await settle()
    const rows = m.wrapper.findAll('tbody tr').map((r) => r.text())
    expect(m.wrapper.find('thead').text()).toContain(copy.admin.colTeam)
    expect(rows[0]).toContain('AX컨설팅2팀')
    expect(rows[0]).toContain(copy.team.owner)
    expect(rows[1]).toContain('AX컨설팅2팀')
    expect(rows[1]).not.toContain(copy.team.owner)
    expect(rows[2]).toContain(copy.admin.noTeam)
  })
})

// 하위 메뉴 정의 (설정·관리자).
import { copy } from '@/copy'

export const SETTINGS_NAV = [
  { to: '/settings/profiles', label: copy.nav.settingsProfiles },
  { to: '/settings/account', label: copy.nav.settingsAccount },
]

export const ADMIN_NAV = [
  { to: '/admin/users', label: copy.nav.adminUsers },
  { to: '/admin/usage', label: copy.nav.adminUsage },
  { to: '/admin/collector', label: copy.nav.adminCollector },
]

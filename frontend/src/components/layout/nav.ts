// 주 메뉴 정의 (SPEC §10.3 사이드바 메뉴). 낙찰 메뉴는 맞춤 추천 다음(§15.7), 모바일은 '더보기' 안.
// 사이드바는 공고 / 낙찰·경쟁 / 도구 세 묶음으로 나눠 보여 준다 (2026-11-18 넓은 화면 개편).
import {
  Building2,
  FolderOpen,
  House,
  MessageSquare,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Swords,
  Trophy,
} from 'lucide-vue-next'
import type { Component } from 'vue'
import { copy } from '@/copy'

export type NavGroupId = 'bids' | 'awards' | 'tools'

export interface NavItem {
  to: string
  match: string // 이 경로로 시작하면 활성 표시 (exact면 같을 때만)
  exact?: boolean
  label: string
  icon: Component
  group: NavGroupId
  adminOnly?: boolean
  mobile: boolean
}

export const NAV_GROUPS: Array<{ id: NavGroupId; label: string }> = [
  { id: 'bids', label: copy.nav.groupBids },
  { id: 'awards', label: copy.nav.groupAwards },
  { id: 'tools', label: copy.nav.groupTools },
]

export const NAV_ITEMS: NavItem[] = [
  { to: '/', match: '/', exact: true, label: copy.nav.home, icon: House, group: 'bids', mobile: true },
  { to: '/search', match: '/search', label: copy.nav.search, icon: Search, group: 'bids', mobile: true },
  { to: '/recommend', match: '/recommend', label: copy.nav.recommend, icon: Sparkles, group: 'bids', mobile: true },
  { to: '/my-awards', match: '/my-awards', label: copy.nav.myAwards, icon: Trophy, group: 'awards', mobile: false },
  { to: '/companies', match: '/companies', label: copy.nav.companies, icon: Building2, group: 'awards', mobile: false },
  {
    to: '/competitors',
    match: '/competitors',
    label: copy.nav.competitors,
    icon: Swords,
    group: 'awards',
    mobile: false,
  },
  {
    to: '/assistant',
    match: '/assistant',
    label: copy.nav.assistant,
    icon: MessageSquare,
    group: 'tools',
    mobile: true,
  },
  { to: '/library', match: '/library', label: copy.nav.library, icon: FolderOpen, group: 'tools', mobile: true },
  {
    to: '/settings/profiles',
    match: '/settings',
    label: copy.nav.settings,
    icon: Settings,
    group: 'tools',
    mobile: false,
  },
  {
    to: '/admin/users',
    match: '/admin',
    label: copy.nav.admin,
    icon: ShieldCheck,
    group: 'tools',
    adminOnly: true,
    mobile: false,
  },
]

/** 묶음별 메뉴. 보여 줄 항목이 없는 묶음은 뺀다. */
export function groupNav(items: NavItem[]): Array<{ id: NavGroupId; label: string; items: NavItem[] }> {
  return NAV_GROUPS.map((g) => ({ ...g, items: items.filter((i) => i.group === g.id) })).filter(
    (g) => g.items.length > 0,
  )
}

/** 지금 경로가 이 메뉴에 속하는가. 홈(/)은 정확히 같을 때만. */
export function isActive(item: NavItem, path: string): boolean {
  return item.exact ? path === item.match : path.startsWith(item.match)
}

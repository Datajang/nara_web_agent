// 주 메뉴 정의 (SPEC §10.3 사이드바 메뉴). 낙찰 메뉴는 맞춤 추천 다음(§15.7), 모바일은 '더보기' 안.
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

export interface NavItem {
  to: string
  match: string // 이 경로로 시작하면 활성 표시 (exact면 같을 때만)
  exact?: boolean
  label: string
  icon: Component
  adminOnly?: boolean
  mobile: boolean
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', match: '/', exact: true, label: copy.nav.home, icon: House, mobile: true },
  { to: '/search', match: '/search', label: copy.nav.search, icon: Search, mobile: true },
  { to: '/recommend', match: '/recommend', label: copy.nav.recommend, icon: Sparkles, mobile: true },
  { to: '/my-awards', match: '/my-awards', label: copy.nav.myAwards, icon: Trophy, mobile: false },
  { to: '/companies', match: '/companies', label: copy.nav.companies, icon: Building2, mobile: false },
  { to: '/competitors', match: '/competitors', label: copy.nav.competitors, icon: Swords, mobile: false },
  { to: '/assistant', match: '/assistant', label: copy.nav.assistant, icon: MessageSquare, mobile: true },
  { to: '/library', match: '/library', label: copy.nav.library, icon: FolderOpen, mobile: true },
  { to: '/settings/profiles', match: '/settings', label: copy.nav.settings, icon: Settings, mobile: false },
  { to: '/admin/users', match: '/admin', label: copy.nav.admin, icon: ShieldCheck, adminOnly: true, mobile: false },
]

/** 지금 경로가 이 메뉴에 속하는가. 홈(/)은 정확히 같을 때만. */
export function isActive(item: NavItem, path: string): boolean {
  return item.exact ? path === item.match : path.startsWith(item.match)
}

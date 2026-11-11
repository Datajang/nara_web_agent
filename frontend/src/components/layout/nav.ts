// 주 메뉴 정의 (SPEC §10.3 사이드바 메뉴 6개).
import { FolderOpen, MessageSquare, Search, Settings, ShieldCheck, Sparkles } from 'lucide-vue-next'
import type { Component } from 'vue'
import { copy } from '@/copy'

export interface NavItem {
  to: string
  match: string // 이 경로로 시작하면 활성 표시
  label: string
  icon: Component
  adminOnly?: boolean
  mobile: boolean
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/search', match: '/search', label: copy.nav.search, icon: Search, mobile: true },
  { to: '/recommend', match: '/recommend', label: copy.nav.recommend, icon: Sparkles, mobile: true },
  { to: '/assistant', match: '/assistant', label: copy.nav.assistant, icon: MessageSquare, mobile: true },
  { to: '/library', match: '/library', label: copy.nav.library, icon: FolderOpen, mobile: true },
  { to: '/settings/profiles', match: '/settings', label: copy.nav.settings, icon: Settings, mobile: false },
  { to: '/admin/users', match: '/admin', label: copy.nav.admin, icon: ShieldCheck, adminOnly: true, mobile: false },
]

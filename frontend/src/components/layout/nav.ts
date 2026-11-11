// 주 메뉴 정의 (SPEC §10.3 사이드바 메뉴 6개).
import { FolderOpen, MessageSquare, Search, Settings, ShieldCheck, Sparkles } from 'lucide-vue-next'
import type { Component } from 'vue'
import { copy } from '@/copy'

export interface NavItem {
  to: string
  label: string
  icon: Component
  adminOnly?: boolean
  mobile: boolean
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/search', label: copy.nav.search, icon: Search, mobile: true },
  { to: '/recommend', label: copy.nav.recommend, icon: Sparkles, mobile: true },
  { to: '/assistant', label: copy.nav.assistant, icon: MessageSquare, mobile: true },
  { to: '/library', label: copy.nav.library, icon: FolderOpen, mobile: true },
  { to: '/settings', label: copy.nav.settings, icon: Settings, mobile: false },
  { to: '/admin/users', label: copy.nav.admin, icon: ShieldCheck, adminOnly: true, mobile: false },
]

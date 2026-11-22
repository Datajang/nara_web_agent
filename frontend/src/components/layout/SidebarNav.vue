<script setup lang="ts">
// 사이드바 (SPEC §10.3): 1024 이상 232px, 768~1023 아이콘만 64px, 768 미만은 숨기고 하단 탭바.
// 메뉴는 공고 / 낙찰·경쟁 / 도구로 묶는다. 아이콘만일 때는 묶음 이름 대신 가는 선 (2026-11-18).
// 1024 이상에서도 로고 옆 < 버튼으로 아이콘만 남기고, 로고 아래 > 버튼으로 다시 펼친다 (2026-11-22).
// 접힌 상태에서는 lg: 펼침 클래스를 아예 빼서 768~1023과 같은 모양이 된다.
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { copy } from '@/copy'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { groupNav, isActive, NAV_ITEMS } from './nav'
import BrandMark from './BrandMark.vue'
import UserMenu from './UserMenu.vue'

const auth = useAuthStore()
const ui = useUiStore()
const route = useRoute()
const emit = defineEmits<{ logout: [] }>()
const groups = computed(() => groupNav(NAV_ITEMS.filter((i) => !i.adminOnly || auth.isAdmin)))
const collapsed = computed(() => ui.sidebarCollapsed)
/** 펼친 상태에서만 붙는 lg: 클래스 */
const wide = (cls: string) => (collapsed.value ? '' : cls)
</script>

<template>
  <aside
    class="sticky top-0 hidden h-screen shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-200 motion-reduce:transition-none md:flex md:w-16"
    :class="wide('lg:w-58')"
    :data-collapsed="collapsed ? 'true' : 'false'"
  >
    <div
      class="flex border-b border-border"
      :class="collapsed ? 'flex-col items-center gap-2 py-3' : 'h-16 items-center lg:pr-3'"
    >
      <RouterLink
        to="/"
        :aria-label="copy.app.home"
        class="flex items-center gap-2.5"
        :class="collapsed ? 'justify-center' : 'h-full min-w-0 flex-1 px-4 lg:pr-2'"
      >
        <BrandMark />
        <span class="sr-only whitespace-nowrap text-md font-semibold tracking-tight text-text" :class="wide('lg:not-sr-only')">
          {{ copy.app.name }}
        </span>
      </RouterLink>
      <button
        type="button"
        data-sidebar-toggle
        class="relative hidden size-8 shrink-0 items-center after:absolute after:-inset-1 after:content-[''] justify-center rounded-control border border-border text-text-2 hover:bg-surface-2 hover:text-text lg:inline-flex"
        :aria-label="collapsed ? copy.nav.expand : copy.nav.collapse"
        :title="collapsed ? copy.nav.expand : copy.nav.collapse"
        :aria-expanded="collapsed ? 'false' : 'true'"
        aria-controls="sidebar-nav"
        @click="ui.toggleSidebar()"
      >
        <ChevronRight v-if="collapsed" class="size-4" aria-hidden="true" />
        <ChevronLeft v-else class="size-4" aria-hidden="true" />
      </button>
    </div>
    <nav id="sidebar-nav" :aria-label="copy.nav.label" class="flex-1 overflow-y-auto px-2 pb-2">
      <div v-for="(g, gi) in groups" :key="g.id" data-nav-group>
        <p
          :id="`nav-group-${g.id}`"
          class="hidden px-3 pb-1 pt-4 text-xs font-semibold tracking-wide text-text-3"
          :class="wide('lg:block')"
        >
          {{ g.label }}
        </p>
        <hr v-if="gi > 0" class="mx-2 my-2 border-border" :class="wide('lg:hidden')" aria-hidden="true" />
        <ul
          class="flex flex-col gap-0.5"
          :aria-labelledby="`nav-group-${g.id}`"
          :class="gi === 0 ? (collapsed ? 'pt-2' : 'pt-2 lg:pt-0') : ''"
        >
          <li v-for="item in g.items" :key="item.to">
            <RouterLink
              :to="item.to"
              class="flex h-10 items-center gap-3 rounded-control px-3 text-base text-text-2 hover:bg-surface-2 hover:text-text"
              :class="isActive(item, route.path) ? '!bg-primary-soft font-semibold !text-primary' : ''"
              :aria-current="isActive(item, route.path) ? 'page' : undefined"
              :title="collapsed ? item.label : undefined"
            >
              <component :is="item.icon" class="size-5 shrink-0" aria-hidden="true" />
              <span class="sr-only" :class="wide('lg:not-sr-only')">{{ item.label }}</span>
            </RouterLink>
          </li>
        </ul>
      </div>
    </nav>
    <div class="border-t border-border p-2">
      <UserMenu :collapsed="collapsed" @logout="emit('logout')" />
    </div>
  </aside>
</template>

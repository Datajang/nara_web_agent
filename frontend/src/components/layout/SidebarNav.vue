<script setup lang="ts">
// 사이드바 (SPEC §10.3): 1024 이상 232px, 768~1023 아이콘만 64px, 768 미만은 숨기고 하단 탭바.
// 메뉴는 공고 / 낙찰·경쟁 / 도구로 묶는다. 아이콘만일 때는 묶음 이름 대신 가는 선 (2026-11-18).
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { copy } from '@/copy'
import { useAuthStore } from '@/stores/auth'
import { groupNav, isActive, NAV_ITEMS } from './nav'
import BrandMark from './BrandMark.vue'
import UserMenu from './UserMenu.vue'

const auth = useAuthStore()
const route = useRoute()
const emit = defineEmits<{ logout: [] }>()
const groups = computed(() => groupNav(NAV_ITEMS.filter((i) => !i.adminOnly || auth.isAdmin)))
</script>

<template>
  <aside
    class="sticky top-0 hidden h-screen shrink-0 flex-col border-r border-border bg-surface md:flex md:w-16 lg:w-58"
  >
    <RouterLink
      to="/"
      :aria-label="copy.app.home"
      class="flex h-16 items-center gap-2.5 border-b border-border px-4"
    >
      <BrandMark />
      <span class="sr-only text-md font-semibold tracking-tight text-text lg:not-sr-only">{{ copy.app.name }}</span>
    </RouterLink>
    <nav :aria-label="copy.nav.label" class="flex-1 overflow-y-auto px-2 pb-2">
      <div v-for="(g, gi) in groups" :key="g.id" data-nav-group>
        <p
          :id="`nav-group-${g.id}`"
          class="hidden px-3 pb-1 pt-4 text-xs font-semibold tracking-wide text-text-3 lg:block"
        >
          {{ g.label }}
        </p>
        <hr v-if="gi > 0" class="mx-2 my-2 border-border lg:hidden" aria-hidden="true" />
        <ul class="flex flex-col gap-0.5" :aria-labelledby="`nav-group-${g.id}`" :class="gi === 0 ? 'pt-2 lg:pt-0' : ''">
          <li v-for="item in g.items" :key="item.to">
            <RouterLink
              :to="item.to"
              class="flex h-10 items-center gap-3 rounded-control px-3 text-base text-text-2 hover:bg-surface-2 hover:text-text"
              :class="isActive(item, route.path) ? '!bg-primary-soft font-semibold !text-primary' : ''"
              :aria-current="isActive(item, route.path) ? 'page' : undefined"
            >
              <component :is="item.icon" class="size-5 shrink-0" aria-hidden="true" />
              <span class="sr-only lg:not-sr-only">{{ item.label }}</span>
            </RouterLink>
          </li>
        </ul>
      </div>
    </nav>
    <div class="border-t border-border p-2">
      <UserMenu @logout="emit('logout')" />
    </div>
  </aside>
</template>

<script setup lang="ts">
// 사이드바 (SPEC §10.3): 1024 이상 232px, 768~1023 아이콘만 64px, 768 미만은 숨기고 하단 탭바.
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { copy } from '@/copy'
import { useAuthStore } from '@/stores/auth'
import { isActive, NAV_ITEMS } from './nav'
import UserMenu from './UserMenu.vue'

const auth = useAuthStore()
const route = useRoute()
const emit = defineEmits<{ logout: [] }>()
const items = computed(() => NAV_ITEMS.filter((i) => !i.adminOnly || auth.isAdmin))
</script>

<template>
  <aside
    class="sticky top-0 hidden h-screen shrink-0 flex-col border-r border-border bg-surface md:flex md:w-16 lg:w-58"
  >
    <RouterLink
      to="/"
      :aria-label="copy.app.home"
      class="flex h-14 items-center gap-2 px-4 text-lg font-semibold text-primary-hover"
    >
      <span
        class="inline-flex size-8 items-center justify-center rounded-control bg-primary text-sm font-semibold text-white"
        aria-hidden="true"
      >N</span>
      <span class="sr-only lg:not-sr-only">{{ copy.app.name }}</span>
    </RouterLink>
    <nav :aria-label="copy.nav.label" class="flex-1 px-2 py-2">
      <ul class="flex flex-col gap-1">
        <li v-for="item in items" :key="item.to">
          <RouterLink
            :to="item.to"
            class="flex h-10 items-center gap-3 rounded-control px-3 text-base text-text-2 hover:bg-surface-2 hover:text-text"
            :class="isActive(item, route.path) ? '!bg-primary-soft !text-primary-hover font-medium' : ''"
            :aria-current="isActive(item, route.path) ? 'page' : undefined"
          >
            <component :is="item.icon" class="size-5 shrink-0" aria-hidden="true" />
            <span class="sr-only lg:not-sr-only">{{ item.label }}</span>
          </RouterLink>
        </li>
      </ul>
    </nav>
    <div class="border-t border-border p-2">
      <UserMenu @logout="emit('logout')" />
    </div>
  </aside>
</template>

<script setup lang="ts">
// 모바일 하단 탭바 (SPEC §10.3): 검색, 추천, 어시스턴트, 내 기록, 더보기.
import {
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuPortal,
  DropdownMenuRoot,
  DropdownMenuTrigger,
} from 'reka-ui'
import { Ellipsis, LogOut } from 'lucide-vue-next'
import { computed } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { copy } from '@/copy'
import { useAuthStore } from '@/stores/auth'
import { NAV_ITEMS } from './nav'

const auth = useAuthStore()
const router = useRouter()
const emit = defineEmits<{ logout: [] }>()
const tabs = NAV_ITEMS.filter((i) => i.mobile)
const more = computed(() => NAV_ITEMS.filter((i) => !i.mobile && (!i.adminOnly || auth.isAdmin)))
const itemClass =
  'flex h-10 cursor-pointer items-center gap-2 rounded-control px-3 text-base text-text outline-none data-[highlighted]:bg-surface-2'
</script>

<template>
  <nav
    :aria-label="copy.nav.label"
    class="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface md:hidden"
  >
    <ul class="grid grid-cols-5">
      <li v-for="tab in tabs" :key="tab.to">
        <RouterLink
          :to="tab.to"
          class="flex h-14 flex-col items-center justify-center gap-0.5 text-xs text-text-2"
          active-class="!text-primary-hover font-medium"
        >
          <component :is="tab.icon" class="size-5" aria-hidden="true" />{{ tab.label }}
        </RouterLink>
      </li>
      <li>
        <DropdownMenuRoot>
          <DropdownMenuTrigger
            class="flex h-14 w-full flex-col items-center justify-center gap-0.5 text-xs text-text-2"
          >
            <Ellipsis class="size-5" aria-hidden="true" />{{ copy.nav.more }}
          </DropdownMenuTrigger>
          <DropdownMenuPortal>
            <DropdownMenuContent
              side="top"
              align="end"
              :side-offset="8"
              class="z-50 min-w-48 rounded-card border border-border bg-surface p-1 shadow-pop"
            >
              <DropdownMenuItem
                v-for="item in more"
                :key="item.to"
                :class="itemClass"
                @select="router.push(item.to)"
              >
                <component :is="item.icon" class="size-4" aria-hidden="true" />{{ item.label }}
              </DropdownMenuItem>
              <DropdownMenuItem :class="itemClass" @select="emit('logout')">
                <LogOut class="size-4" aria-hidden="true" />{{ copy.nav.logout }}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenuPortal>
        </DropdownMenuRoot>
      </li>
    </ul>
  </nav>
</template>

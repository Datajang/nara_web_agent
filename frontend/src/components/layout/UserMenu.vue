<script setup lang="ts">
// 사이드바 하단 사용자 메뉴. 태블릿(64px)에서는 아바타만 보인다.
import {
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuPortal,
  DropdownMenuRoot,
  DropdownMenuTrigger,
} from 'reka-ui'
import { CircleUser, LogOut } from 'lucide-vue-next'
import { copy } from '@/copy'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const emit = defineEmits<{ logout: [] }>()
</script>

<template>
  <DropdownMenuRoot>
    <DropdownMenuTrigger
      class="flex h-12 w-full items-center gap-3 rounded-control px-3 text-left text-base text-text-2 hover:bg-surface-2 hover:text-text"
      :aria-label="copy.nav.userMenu"
    >
      <CircleUser class="size-5 shrink-0" aria-hidden="true" />
      <span class="hidden min-w-0 flex-1 lg:block">
        <span class="block truncate font-medium text-text">{{ auth.me?.display_name || auth.me?.email }}</span>
        <span class="block text-xs text-text-3">
          {{ auth.isAdmin ? copy.nav.roleAdmin : copy.nav.roleMember }}
        </span>
      </span>
    </DropdownMenuTrigger>
    <DropdownMenuPortal>
      <DropdownMenuContent
        side="top"
        align="start"
        :side-offset="8"
        class="z-50 min-w-48 rounded-card border border-border bg-surface p-1 shadow-pop"
      >
        <p class="truncate px-3 py-2 text-sm text-text-3">{{ auth.me?.email }}</p>
        <DropdownMenuItem
          class="flex h-10 cursor-pointer items-center gap-2 rounded-control px-3 text-base text-text outline-none data-[highlighted]:bg-surface-2"
          @select="emit('logout')"
        >
          <LogOut class="size-4" aria-hidden="true" />{{ copy.nav.logout }}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenuPortal>
  </DropdownMenuRoot>
</template>

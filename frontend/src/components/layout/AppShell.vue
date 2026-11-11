<script setup lang="ts">
// 앱 셸 (SPEC §10.3): 사이드바 + 상단 바 + 본문(최대 1200px, 여백 24).
import { computed } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { copy } from '@/copy'
import { useAuthStore } from '@/stores/auth'
import MobileTabBar from './MobileTabBar.vue'
import SidebarNav from './SidebarNav.vue'
import TopBar from './TopBar.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const title = computed(() => route.meta.title ?? copy.app.name)

async function logout() {
  await auth.logout()
  await router.replace('/login')
}
</script>

<template>
  <div class="flex min-h-screen bg-bg">
    <a
      href="#main"
      class="sr-only z-50 rounded-control bg-surface px-4 py-2 text-primary focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
    >{{ copy.app.skipToContent }}</a>
    <SidebarNav @logout="logout" />
    <div class="flex min-w-0 flex-1 flex-col">
      <TopBar :title="title" />
      <main id="main" tabindex="-1" class="mx-auto w-full max-w-[1200px] flex-1 p-4 pb-24 md:p-6">
        <RouterView />
      </main>
    </div>
    <MobileTabBar @logout="logout" />
  </div>
</template>

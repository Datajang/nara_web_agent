<script setup lang="ts">
// 초대 수락 (SPEC §13 P6). /join?code= 로 온다. 로그인 전이면 라우터 가드가 로그인 뒤 여기로 되돌린다.
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { Users } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { authApi } from '@/api/auth'
import { teamsApi } from '@/api/teams'
import UiButton from '@/components/ui/UiButton.vue'
import { copy } from '@/copy'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { generalMessage } from '@/utils/authErrors'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const queryClient = useQueryClient()
const team = useQuery({ queryKey: ['team'], queryFn: () => teamsApi.me() })
const code = computed(() => (typeof route.query.code === 'string' ? route.query.code.trim() : ''))
const error = ref('')
const joining = ref(false)

async function join() {
  error.value = ''
  joining.value = true
  try {
    await teamsApi.join(code.value)
    auth.me = await authApi.me()
    void queryClient.invalidateQueries({ queryKey: ['team'] })
    void queryClient.invalidateQueries({ queryKey: ['profiles'] })
    ui.toast(copy.team.joined, 'success')
    await router.push('/settings/team')
  } catch (e) {
    error.value = generalMessage(e)
  } finally {
    joining.value = false
  }
}
</script>

<template>
  <section class="mx-auto flex max-w-md flex-col items-center gap-4 rounded-card border border-border bg-surface p-8 text-center">
    <span class="inline-flex size-12 items-center justify-center rounded-full bg-primary-soft text-primary">
      <Users class="size-6" aria-hidden="true" />
    </span>
    <template v-if="!code">
      <p class="text-base text-text-2">{{ copy.team.noCode }}</p>
    </template>
    <template v-else-if="team.data.value?.team">
      <p class="text-base text-text-2">{{ copy.team.alreadyInTeam }}</p>
      <RouterLink to="/settings/team" class="text-base font-medium text-primary-hover hover:underline">
        {{ copy.team.title }}
      </RouterLink>
    </template>
    <template v-else-if="team.data.value">
      <p class="text-md text-text">{{ copy.team.joinLead(code) }}</p>
      <p v-if="error" class="text-sm text-danger-fg" role="alert">{{ error }}</p>
      <UiButton :loading="joining" @click="join">{{ copy.team.joinSubmit }}</UiButton>
    </template>
  </section>
</template>

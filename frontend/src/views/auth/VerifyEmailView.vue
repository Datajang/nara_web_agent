<script setup lang="ts">
// 메일 링크(/verify-email?token=)로 들어오면 토큰을 POST해 상태를 전이한다 (§9.2-3).
import { onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { authApi, type UserStatus } from '@/api/auth'
import AuthCard from '@/components/auth/AuthCard.vue'
import { copy } from '@/copy'

const route = useRoute()
const state = ref<'loading' | 'failed' | UserStatus>('loading')

onMounted(async () => {
  const token = typeof route.query.token === 'string' ? route.query.token : ''
  if (!token) {
    state.value = 'failed'
    return
  }
  try {
    state.value = (await authApi.verifyEmail(token)).status
  } catch {
    state.value = 'failed'
  }
})
</script>

<template>
  <AuthCard v-if="state === 'loading'" :title="copy.auth.verifyingTitle" :subtitle="copy.common.loading" />
  <AuthCard
    v-else-if="state === 'failed'"
    :title="copy.auth.verifyFailedTitle"
    :subtitle="copy.auth.verifyFailedBody"
  >
    <template #footer>
      <RouterLink class="text-primary hover:underline" to="/login">{{ copy.auth.toLogin }}</RouterLink>
    </template>
  </AuthCard>
  <AuthCard
    v-else-if="state === 'pending_approval'"
    :title="copy.auth.pendingApprovalTitle"
    :subtitle="copy.auth.pendingApprovalBody"
  >
    <template #footer>
      <RouterLink class="text-primary hover:underline" to="/login">{{ copy.auth.toLogin }}</RouterLink>
    </template>
  </AuthCard>
  <AuthCard v-else :title="copy.auth.verifiedTitle" :subtitle="copy.auth.verifiedBody">
    <template #footer>
      <RouterLink class="text-primary hover:underline" to="/login">{{ copy.auth.toLogin }}</RouterLink>
    </template>
  </AuthCard>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { ApiError } from '@/api/client'
import AuthCard from '@/components/auth/AuthCard.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import { copy } from '@/copy'
import { safeNext } from '@/router'
import { useAuthStore } from '@/stores/auth'
import { generalMessage } from '@/utils/authErrors'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const email = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function onSubmit() {
  error.value = ''
  busy.value = true
  try {
    await auth.login(email.value, password.value)
    await router.replace(safeNext(route.query.next))
  } catch (e) {
    if (!(e instanceof ApiError)) {
      error.value = copy.common.networkError
    } else if (e.code === 'invalid_credentials') {
      error.value = copy.auth.invalid
    } else if (e.code === 'account_locked') {
      error.value = copy.auth.locked
    } else if (e.code === 'email_not_verified') {
      await router.push({ path: '/register/check-email', query: { email: email.value } })
    } else if (e.code === 'pending_approval') {
      await router.push('/pending-approval')
    } else if (e.code === 'disabled') {
      error.value = copy.auth.disabled
    } else {
      error.value = generalMessage(e)
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthCard :title="copy.auth.loginTitle" :subtitle="copy.auth.loginSubtitle">
    <form class="flex flex-col gap-4" novalidate @submit.prevent="onSubmit">
      <UiInput v-model="email" :label="copy.auth.email" type="email" autocomplete="email" required />
      <UiInput
        v-model="password"
        :label="copy.auth.password"
        type="password"
        autocomplete="current-password"
        required
      />
      <p
        v-if="error"
        role="alert"
        class="rounded-control bg-danger-bg px-3 py-2 text-base text-danger-fg"
      >{{ error }}</p>
      <UiButton type="submit" :loading="busy" block>{{ copy.auth.submitLogin }}</UiButton>
    </form>
    <template #footer>
      <RouterLink class="text-primary hover:underline" to="/register">{{ copy.auth.toRegister }}</RouterLink>
      <RouterLink class="text-text-2 hover:underline" to="/forgot-password">{{ copy.auth.toForgot }}</RouterLink>
    </template>
  </AuthCard>
</template>

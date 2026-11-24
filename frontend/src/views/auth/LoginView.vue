<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { ApiError } from '@/api/client'
import AuthCard from '@/components/auth/AuthCard.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import { copy } from '@/copy'
import { safeNext } from '@/router'
import { useAuthStore } from '@/stores/auth'
import { generalMessage } from '@/utils/authErrors'
import { forgetRememberedEmail, readRememberedEmail, saveRememberedEmail } from '@/utils/rememberedEmail'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const remembered = readRememberedEmail()
const email = ref(remembered)
const password = ref('')
const remember = ref(remembered !== '')
const error = ref('')
const busy = ref(false)
const form = ref<HTMLFormElement | null>(null)

// 기억한 이메일이 있으면 바로 비밀번호를 칠 수 있게
onMounted(() => {
  if (remembered) form.value?.querySelector<HTMLInputElement>('input[type="password"]')?.focus()
})
// 체크를 풀면 로그인하지 않아도 바로 지운다(공용 PC)
watch(remember, (on) => {
  if (!on) forgetRememberedEmail()
})

async function onSubmit() {
  error.value = ''
  busy.value = true
  try {
    await auth.login(email.value, password.value)
    if (remember.value) saveRememberedEmail(email.value.trim())
    else forgetRememberedEmail()
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
  <AuthCard :title="copy.auth.loginTitle" :subtitle="copy.auth.loginLead">
    <form ref="form" class="flex flex-col gap-4.5" novalidate @submit.prevent="onSubmit">
      <UiInput
        v-model="email"
        :label="copy.auth.email"
        type="email"
        autocomplete="email"
        size="lg"
        :placeholder="copy.auth.emailPlaceholder"
        required
      />
      <UiInput
        v-model="password"
        :label="copy.auth.password"
        type="password"
        autocomplete="current-password"
        size="lg"
        required
      />
      <label class="inline-flex min-h-6 items-center gap-2 self-start text-base text-text-2">
        <input v-model="remember" name="remember-email" type="checkbox" class="size-4 accent-primary" />
        {{ copy.auth.rememberEmail }}
      </label>
      <p
        v-if="error"
        role="alert"
        class="rounded-control bg-danger-bg px-3 py-2 text-base text-danger-fg"
      >{{ error }}</p>
      <UiButton class="mt-2" type="submit" size="lg" :loading="busy" block>{{ copy.auth.submitLogin }}</UiButton>
      <p class="text-center text-sm text-text-2">
        {{ copy.auth.forgotPrompt }}
        <RouterLink class="ml-1 font-semibold text-primary hover:underline" to="/forgot-password">{{ copy.auth.toForgot }}</RouterLink>
      </p>
    </form>
    <template #footer>
      <p>
        {{ copy.auth.noAccount }}
        <RouterLink class="font-semibold text-primary hover:underline" to="/register">{{ copy.auth.registerLink }}</RouterLink>
      </p>
    </template>
  </AuthCard>
</template>

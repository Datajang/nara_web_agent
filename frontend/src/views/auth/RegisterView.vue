<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import AuthCard from '@/components/auth/AuthCard.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import { copy } from '@/copy'
import { generalMessage, passwordMessage } from '@/utils/authErrors'

const router = useRouter()
const email = ref('')
const displayName = ref('')
const password = ref('')
const passwordConfirm = ref('')
const errors = ref<{ email?: string; password?: string; confirm?: string; form?: string }>({})
const busy = ref(false)

async function onSubmit() {
  errors.value = {}
  // 비밀번호 확인(2026-11-23): 서버에 보내기 전에 화면에서 맞춘다
  if (password.value !== passwordConfirm.value) {
    errors.value = { confirm: copy.auth.passwordMismatch }
    return
  }
  busy.value = true
  try {
    await authApi.register({
      email: email.value,
      password: password.value,
      display_name: displayName.value,
    })
    await router.push({ path: '/register/check-email', query: { email: email.value.trim() } })
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) {
      errors.value = {
        email:
          e.reason('email') === 'domain_not_allowed'
            ? copy.auth.domainNotAllowed
            : e.reason('email')
              ? copy.auth.invalidInput
              : undefined,
        password: passwordMessage(e),
      }
      if (!errors.value.email && !errors.value.password) errors.value.form = copy.auth.invalidInput
    } else {
      errors.value = { form: generalMessage(e) }
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthCard :title="copy.auth.registerTitle" :subtitle="copy.auth.registerSubtitle" aside="steps" :step="1">
    <form class="flex flex-col gap-4.5" novalidate @submit.prevent="onSubmit">
      <UiInput
        v-model="email"
        :label="copy.auth.email"
        type="email"
        autocomplete="email"
        size="lg"
        :placeholder="copy.auth.emailPlaceholder"
        required
        :error="errors.email"
      />
      <UiInput
        v-model="displayName"
        :label="`${copy.auth.displayName} ${copy.auth.optional}`"
        autocomplete="name"
        size="lg"
        :placeholder="copy.auth.displayNamePlaceholder"
        :max-length="50"
      />
      <UiInput
        v-model="password"
        :label="copy.auth.password"
        type="password"
        autocomplete="new-password"
        size="lg"
        required
        :hint="copy.auth.passwordHint"
        :error="errors.password"
      />
      <UiInput
        v-model="passwordConfirm"
        :label="copy.auth.passwordConfirm"
        type="password"
        autocomplete="new-password"
        size="lg"
        required
        :error="errors.confirm"
      />
      <p
        v-if="errors.form"
        role="alert"
        class="rounded-control bg-danger-bg px-3 py-2 text-base text-danger-fg"
      >{{ errors.form }}</p>
      <UiButton class="mt-2" type="submit" size="lg" :loading="busy" block>{{ copy.auth.submitRegister }}</UiButton>
    </form>
    <template #footer>
      <p>
        {{ copy.auth.hasAccount }}
        <RouterLink class="font-semibold text-primary hover:underline" to="/login">{{ copy.auth.loginLink }}</RouterLink>
      </p>
    </template>
  </AuthCard>
</template>

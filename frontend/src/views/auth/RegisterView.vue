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
const errors = ref<{ email?: string; password?: string; form?: string }>({})
const busy = ref(false)

async function onSubmit() {
  errors.value = {}
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
  <AuthCard :title="copy.auth.registerTitle" :subtitle="copy.auth.registerSubtitle">
    <form class="flex flex-col gap-4" novalidate @submit.prevent="onSubmit">
      <UiInput
        v-model="email"
        :label="copy.auth.email"
        type="email"
        autocomplete="email"
        required
        :error="errors.email"
      />
      <UiInput
        v-model="displayName"
        :label="copy.auth.displayName"
        autocomplete="name"
        :hint="copy.auth.displayNameHint"
        :max-length="50"
      />
      <UiInput
        v-model="password"
        :label="copy.auth.password"
        type="password"
        autocomplete="new-password"
        required
        :hint="copy.auth.passwordHint"
        :error="errors.password"
      />
      <p
        v-if="errors.form"
        role="alert"
        class="rounded-control bg-danger-bg px-3 py-2 text-base text-danger-fg"
      >{{ errors.form }}</p>
      <UiButton type="submit" :loading="busy" block>{{ copy.auth.submitRegister }}</UiButton>
    </form>
    <template #footer>
      <RouterLink class="text-primary hover:underline" to="/login">{{ copy.auth.toLogin }}</RouterLink>
    </template>
  </AuthCard>
</template>

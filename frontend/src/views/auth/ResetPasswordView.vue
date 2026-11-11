<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import AuthCard from '@/components/auth/AuthCard.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import { copy } from '@/copy'
import { generalMessage, passwordMessage } from '@/utils/authErrors'

const route = useRoute()
const token = computed(() => (typeof route.query.token === 'string' ? route.query.token : ''))
const password = ref('')
const done = ref(false)
const fieldError = ref('')
const error = ref('')
const busy = ref(false)

async function onSubmit() {
  fieldError.value = ''
  error.value = ''
  busy.value = true
  try {
    await authApi.resetPassword(token.value, password.value)
    done.value = true
  } catch (e) {
    if (e instanceof ApiError && e.code === 'invalid_token') error.value = copy.auth.resetInvalid
    else if (e instanceof ApiError && e.status === 422) fieldError.value = passwordMessage(e) ?? copy.auth.invalidInput
    else error.value = generalMessage(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthCard
    :title="copy.auth.resetTitle"
    :subtitle="done ? copy.auth.resetDone : !token ? copy.auth.missingToken : undefined"
  >
    <form v-if="token && !done" class="flex flex-col gap-4" novalidate @submit.prevent="onSubmit">
      <UiInput
        v-model="password"
        :label="copy.auth.newPassword"
        type="password"
        autocomplete="new-password"
        required
        :hint="copy.auth.passwordHint"
        :error="fieldError"
      />
      <p v-if="error" role="alert" class="rounded-control bg-danger-bg px-3 py-2 text-base text-danger-fg">
        {{ error }}
      </p>
      <UiButton type="submit" :loading="busy" block>{{ copy.auth.resetSubmit }}</UiButton>
    </form>
    <template #footer>
      <RouterLink class="text-primary hover:underline" to="/login">{{ copy.auth.toLogin }}</RouterLink>
      <RouterLink v-if="error" class="text-text-2 hover:underline" to="/forgot-password">
        {{ copy.auth.forgotSubmit }}
      </RouterLink>
    </template>
  </AuthCard>
</template>

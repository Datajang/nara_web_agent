<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { authApi } from '@/api/auth'
import AuthCard from '@/components/auth/AuthCard.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import { copy } from '@/copy'
import { generalMessage } from '@/utils/authErrors'

const email = ref('')
const sent = ref(false)
const error = ref('')
const busy = ref(false)

async function onSubmit() {
  error.value = ''
  busy.value = true
  try {
    await authApi.forgotPassword(email.value)
    sent.value = true
  } catch (e) {
    error.value = generalMessage(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthCard :title="copy.auth.forgotTitle" :subtitle="sent ? copy.auth.forgotSent : copy.auth.forgotSubtitle">
    <form v-if="!sent" class="flex flex-col gap-4" novalidate @submit.prevent="onSubmit">
      <UiInput v-model="email" :label="copy.auth.email" type="email" autocomplete="email" required />
      <p v-if="error" role="alert" class="rounded-control bg-danger-bg px-3 py-2 text-base text-danger-fg">
        {{ error }}
      </p>
      <UiButton type="submit" :loading="busy" block>{{ copy.auth.forgotSubmit }}</UiButton>
    </form>
    <template #footer>
      <RouterLink class="text-primary hover:underline" to="/login">{{ copy.auth.toLogin }}</RouterLink>
    </template>
  </AuthCard>
</template>

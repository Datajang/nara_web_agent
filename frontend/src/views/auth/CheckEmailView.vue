<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { authApi } from '@/api/auth'
import AuthCard from '@/components/auth/AuthCard.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { copy } from '@/copy'
import { useUiStore } from '@/stores/ui'
import { generalMessage } from '@/utils/authErrors'

const route = useRoute()
const ui = useUiStore()
const email = computed(() => (typeof route.query.email === 'string' ? route.query.email : ''))
const busy = ref(false)

async function resend() {
  busy.value = true
  try {
    await authApi.resendVerification(email.value)
    ui.toast(copy.auth.resent, 'success')
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthCard :title="copy.auth.checkEmailTitle" aside="steps" :step="2" icon="mail">
    <template #subtitle>
      <p v-if="email">
        <strong class="font-semibold text-text">{{ copy.auth.checkEmailSent(email) }}</strong>
        {{ copy.auth.checkEmailAction }}
      </p>
      <p v-else>{{ copy.auth.checkEmailBodyNoAddress }}</p>
    </template>
    <p class="rounded-control bg-warning-bg px-3.5 py-3 text-base text-warning-fg">{{ copy.auth.checkEmailSpam }}</p>
    <UiButton v-if="email" class="mt-6" variant="secondary" size="lg" block :loading="busy" @click="resend">
      {{ copy.auth.resend }}
    </UiButton>
    <template #footer>
      <p>
        {{ copy.auth.wrongAddress }}
        <RouterLink class="font-semibold text-primary hover:underline" to="/register">{{ copy.auth.registerAgain }}</RouterLink>
      </p>
      <RouterLink class="text-primary hover:underline" to="/login">{{ copy.auth.toLogin }}</RouterLink>
    </template>
  </AuthCard>
</template>

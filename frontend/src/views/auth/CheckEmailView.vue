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
  <AuthCard
    :title="copy.auth.checkEmailTitle"
    :subtitle="email ? copy.auth.checkEmailBody(email) : copy.auth.checkEmailBodyNoAddress"
  >
    <UiButton v-if="email" variant="secondary" block :loading="busy" @click="resend">
      {{ copy.auth.resend }}
    </UiButton>
    <template #footer>
      <RouterLink class="text-primary hover:underline" to="/login">{{ copy.auth.toLogin }}</RouterLink>
    </template>
  </AuthCard>
</template>

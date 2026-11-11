<script setup lang="ts">
// 계정 설정 (SPEC §7.8): 이름 변경, 비밀번호 변경(현재 비밀번호 필요), 로그아웃.
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import SubNav from '@/components/layout/SubNav.vue'
import { SETTINGS_NAV } from '@/components/layout/subnavs'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import { copy } from '@/copy'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { generalMessage, passwordMessage } from '@/utils/authErrors'

const auth = useAuthStore()
const ui = useUiStore()
const router = useRouter()
const name = ref(auth.me?.display_name ?? '')
const current = ref('')
const next = ref('')
const pwError = ref('')
const saving = ref(false)

async function saveName() {
  saving.value = true
  try {
    auth.me = await authApi.updateMe({ display_name: name.value.trim() })
    ui.toast(copy.account.nameSaved, 'success')
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  } finally {
    saving.value = false
  }
}

async function changePassword() {
  pwError.value = ''
  try {
    auth.me = await authApi.updateMe({ current_password: current.value, new_password: next.value })
    current.value = ''
    next.value = ''
    ui.toast(copy.account.passwordChanged, 'success')
  } catch (e) {
    if (e instanceof ApiError && e.code === 'invalid_password') pwError.value = copy.account.wrongPassword
    else if (e instanceof ApiError && e.status === 422)
      pwError.value = passwordMessage(e, 'new_password') ?? copy.auth.invalidInput
    else pwError.value = generalMessage(e)
  }
}

async function logout() {
  await auth.logout()
  await router.replace('/login')
}
</script>

<template>
  <div class="flex max-w-xl flex-col gap-4">
    <SubNav :label="copy.nav.settingsLabel" :items="SETTINGS_NAV" />
    <form class="flex flex-col gap-3 rounded-card border border-border bg-surface p-4" @submit.prevent="saveName">
      <UiInput v-model="name" :label="copy.auth.displayName" :max-length="50" />
      <div><UiButton type="submit" :loading="saving">{{ copy.common.save }}</UiButton></div>
    </form>
    <form class="flex flex-col gap-3 rounded-card border border-border bg-surface p-4" @submit.prevent="changePassword">
      <UiInput v-model="current" type="password" autocomplete="current-password" :label="copy.account.currentPassword" />
      <UiInput
        v-model="next"
        type="password"
        autocomplete="new-password"
        :label="copy.auth.newPassword"
        :hint="copy.auth.passwordHint"
        :error="pwError"
      />
      <div><UiButton type="submit" :disabled="!current || !next">{{ copy.account.changePassword }}</UiButton></div>
    </form>
    <div><UiButton variant="secondary" @click="logout">{{ copy.nav.logout }}</UiButton></div>
  </div>
</template>

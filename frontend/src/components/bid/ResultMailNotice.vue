<script setup lang="ts">
// 북마크 직후 '결과가 나오면 메일로 알려드려요' 팝업 (2026-11-25). App에 한 번만 둔다.
import { computed, ref, watch } from 'vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiModal from '@/components/ui/UiModal.vue'
import { copy } from '@/copy'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { hideNoticeForever } from '@/utils/resultMailNotice'

const ui = useUiStore()
const auth = useAuthStore()
const hide = ref(false)
const open = computed({
  get: () => ui.resultNotice !== null,
  set: (v: boolean) => {
    if (!v) close()
  },
})
watch(
  () => ui.resultNotice,
  () => (hide.value = false),
)

function close() {
  if (hide.value) hideNoticeForever()
  ui.resultNotice = null
}
</script>

<template>
  <UiModal v-model:open="open" :title="copy.resultMail.noticeTitle">
    <p class="text-base text-text-2">
      {{ ui.resultNotice?.watching === false ? copy.resultMail.noticeNoOpening : copy.resultMail.noticeBody(auth.me?.email ?? '') }}
    </p>
    <label class="mt-4 inline-flex items-center gap-2 text-sm text-text-2">
      <input v-model="hide" name="result-mail-hide" type="checkbox" class="size-4 accent-primary" />
      {{ copy.resultMail.hideForever }}
    </label>
    <template #actions>
      <UiButton data-result-mail-ok @click="close">{{ copy.resultMail.ok }}</UiButton>
    </template>
  </UiModal>
</template>

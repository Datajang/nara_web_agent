<script setup lang="ts">
// 입찰공고 목록 다운로드 (2026-11-22): 관심 공고·공고 검색·맞춤 추천에서 지금 보이는 공고를 엑셀로.
// 최대 500건(검색 상한). 엑셀은 서버가 만든다(용역 구분·조달분류·공고문 링크는 원본 데이터에만 있다).
import { Download } from 'lucide-vue-next'
import { ref } from 'vue'
import { bidsApi } from '@/api/bids'
import UiButton from '@/components/ui/UiButton.vue'
import { copy } from '@/copy'
import { useUiStore } from '@/stores/ui'
import { generalMessage } from '@/utils/authErrors'
import { exportFilename } from '@/utils/exportFilename'
import { saveBlob } from '@/utils/saveBlob'

const props = defineProps<{ bidIds: string[] }>()
const ui = useUiStore()
const busy = ref(false)

async function download() {
  busy.value = true
  try {
    saveBlob(await bidsApi.exportList(props.bidIds), exportFilename())
    ui.toast(copy.exportList.done, 'success')
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <UiButton
    size="sm"
    variant="secondary"
    :loading="busy"
    :disabled="!bidIds.length"
    :title="copy.exportList.label"
    data-export
    @click="download"
  >
    <Download class="size-4" aria-hidden="true" />
    <span>{{ copy.exportList.button }}</span>
  </UiButton>
</template>

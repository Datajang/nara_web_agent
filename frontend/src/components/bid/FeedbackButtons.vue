<script setup lang="ts">
// 👍·👎 피드백 (SPEC §7.5-6, §10.4, §12.7). 👎는 사유 코드를 고르고, 의견은 선택으로 남긴다.
import { ThumbsDown, ThumbsUp } from 'lucide-vue-next'
import { computed, ref, useId } from 'vue'
import { bidsApi } from '@/api/bids'
import type { FeedbackIn } from '@/api/types'
import UiButton from '@/components/ui/UiButton.vue'
import UiTextarea from '@/components/ui/UiTextarea.vue'
import { copy } from '@/copy'
import { useUiStore } from '@/stores/ui'
import { generalMessage } from '@/utils/authErrors'

const props = defineProps<{ targetType: FeedbackIn['target_type']; targetId: number }>()
type Reason = NonNullable<FeedbackIn['reason']>
const REASONS: Reason[] = ['wrong', 'missing', 'irrelevant', 'too_long', 'other']
const rating = ref<1 | -1 | null>(null)
const reason = ref<Reason | null>(null)
const radioName = useId()
const canSubmit = computed(() => rating.value === 1 || (rating.value === -1 && reason.value !== null))
const comment = ref('')
const sent = ref(false)
const sending = ref(false)
const ui = useUiStore()

async function submit() {
  if (!canSubmit.value || rating.value === null) return
  sending.value = true
  try {
    await bidsApi.feedback({
      target_type: props.targetType,
      target_id: props.targetId,
      rating: rating.value,
      reason: rating.value === -1 ? reason.value : null,
      comment: comment.value.trim() || null,
    })
    sent.value = true
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-3 rounded-card border border-border bg-surface p-4">
    <p v-if="sent" class="text-base text-success-fg" role="status">{{ copy.feedback.thanks }}</p>
    <template v-else>
      <div class="flex items-center gap-2">
        <span class="text-base text-text-2">{{ copy.feedback.label }}</span>
        <button
          v-for="opt in [
            { v: 1 as const, label: copy.feedback.up, icon: ThumbsUp },
            { v: -1 as const, label: copy.feedback.down, icon: ThumbsDown },
          ]"
          :key="opt.v"
          type="button"
          class="inline-flex size-10 items-center justify-center rounded-control border border-border-input hover:bg-surface-2 aria-pressed:bg-primary-soft aria-pressed:text-primary-hover"
          :aria-label="opt.label"
          :aria-pressed="rating === opt.v"
          @click="rating = opt.v"
        >
          <component :is="opt.icon" class="size-4" aria-hidden="true" />
        </button>
      </div>
      <template v-if="rating !== null">
        <fieldset v-if="rating === -1" role="radiogroup" :aria-label="copy.feedback.reasonLabel" class="flex flex-col gap-1.5">
          <legend class="mb-1.5 text-base font-medium text-text">{{ copy.feedback.reasonLabel }}</legend>
          <div class="flex flex-wrap gap-2">
            <label
              v-for="r in REASONS"
              :key="r"
              class="inline-flex h-9 cursor-pointer items-center rounded-control border border-border-input px-3 text-sm has-[:checked]:border-primary has-[:checked]:bg-primary-soft has-[:checked]:text-primary-hover has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-primary"
            >
              <input v-model="reason" class="sr-only" type="radio" :name="radioName" :value="r" />
              {{ copy.feedback.reasons[r] }}
            </label>
          </div>
        </fieldset>
        <UiTextarea v-model="comment" :label="copy.feedback.comment" :max-length="1000" :rows="2" />
        <div><UiButton size="sm" :loading="sending" :disabled="!canSubmit" @click="submit">{{ copy.feedback.submit }}</UiButton></div>
      </template>
    </template>
  </div>
</template>

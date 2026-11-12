<script setup lang="ts">
// 관심 키워드 설정 (SPEC §13 P6). 팀 키워드(팀 프로필, 읽기 전용) + 내 키워드가 합쳐 3개 이상이어야 한다.
import { useQuery } from '@tanstack/vue-query'
import { Users } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { authApi } from '@/api/auth'
import { profilesApi } from '@/api/profiles'
import { teamsApi } from '@/api/teams'
import ChipInput from '@/components/ui/ChipInput.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { copy } from '@/copy'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { generalMessage } from '@/utils/authErrors'

const MIN = 3
const auth = useAuthStore()
const ui = useUiStore()
const router = useRouter()
const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => profilesApi.list() })
const team = useQuery({ queryKey: ['team'], queryFn: () => teamsApi.me() })
const mine = ref<string[]>([...(auth.me?.interest_keywords ?? [])])
const chips = ref<InstanceType<typeof ChipInput> | null>(null)
const saving = ref(false)

const teamKeywords = computed(() => {
  const all = (profiles.data.value?.items ?? []).filter((p) => p.scope === 'team').flatMap((p) => p.keywords)
  return [...new Set(all)]
})
const count = computed(() => new Set([...teamKeywords.value, ...mine.value]).size)

async function save() {
  chips.value?.commit()
  saving.value = true
  try {
    auth.me = await authApi.updateMe({ interest_keywords: mine.value })
    ui.toast(copy.onboarding.saved, 'success')
    await router.push('/')
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="flex max-w-2xl flex-col gap-6">
    <p class="text-md text-text-2">{{ copy.onboarding.lead }}</p>

    <section class="flex flex-col gap-5 rounded-card border border-border bg-surface p-5">
      <div v-if="teamKeywords.length" class="flex flex-col gap-1.5">
        <p class="text-base font-medium text-text">{{ copy.onboarding.teamLabel }}</p>
        <p class="flex flex-wrap gap-1.5">
          <span
            v-for="k in teamKeywords"
            :key="k"
            class="inline-flex h-7 items-center rounded-full bg-surface-2 px-3 text-sm text-text-2"
          >{{ k }}</span>
        </p>
        <p class="text-sm text-text-3">{{ copy.onboarding.teamHint }}</p>
      </div>
      <ChipInput
        ref="chips"
        v-model="mine"
        :label="copy.onboarding.personalLabel"
        :hint="copy.onboarding.personalHint"
        :max="10"
        :max-length="30"
      />
      <div class="flex flex-wrap items-center justify-between gap-3">
        <span class="text-sm tabular" :class="count >= MIN ? 'text-success-fg' : 'text-text-3'">
          {{ copy.onboarding.count(count) }}
        </span>
        <UiButton :disabled="count < MIN" :loading="saving" @click="save">{{ copy.onboarding.save }}</UiButton>
      </div>
    </section>

    <section v-if="team.data.value && !team.data.value.team" class="flex items-start gap-3 rounded-card bg-surface-2 p-5">
      <Users class="mt-0.5 size-5 shrink-0 text-primary" aria-hidden="true" />
      <div class="flex flex-col gap-1">
        <h3 class="text-base font-semibold text-text">{{ copy.onboarding.teamTitle }}</h3>
        <p class="text-base text-text-2">{{ copy.onboarding.teamLead }}</p>
        <RouterLink to="/settings/team" class="mt-1 text-base font-medium text-primary-hover hover:underline">
          {{ copy.onboarding.goTeam }}
        </RouterLink>
      </div>
    </section>
  </div>
</template>

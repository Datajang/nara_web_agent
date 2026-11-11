<script setup lang="ts">
// 프로필 설정 (SPEC §7.8). 키워드는 추천 후보에만 쓰이고 profile_hash에 들어가지 않는다.
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref } from 'vue'
import { profilesApi } from '@/api/profiles'
import type { Profile } from '@/api/types'
import SubNav from '@/components/layout/SubNav.vue'
import { SETTINGS_NAV } from '@/components/layout/subnavs'
import ChipInput from '@/components/ui/ChipInput.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiModal from '@/components/ui/UiModal.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import UiTextarea from '@/components/ui/UiTextarea.vue'
import { copy } from '@/copy'
import { useUiStore } from '@/stores/ui'
import { generalMessage } from '@/utils/authErrors'
import { formatDateTime } from '@/utils/format'

interface Draft {
  id: number | null
  name: string
  description: string
  keywords: string[]
  is_default: boolean
  original: string
}

const ui = useUiStore()
const queryClient = useQueryClient()
const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => profilesApi.list() })
const draft = ref<Draft | null>(null)
const saving = ref(false)
const suggesting = ref(false)
const removing = ref<Profile | null>(null)
const chips = ref<InstanceType<typeof ChipInput> | null>(null)

function startNew() {
  draft.value = {
    id: null,
    name: '',
    description: '',
    keywords: [],
    is_default: !profiles.data.value?.items.length,
    original: '',
  }
}
function startEdit(p: Profile) {
  draft.value = {
    id: p.id,
    name: p.name,
    description: p.description,
    keywords: [...p.keywords],
    is_default: p.is_default,
    original: p.description,
  }
}
const descriptionChanged = computed(
  () => !!draft.value?.id && draft.value.description.trim() !== draft.value.original.trim(),
)

async function suggest() {
  if (!draft.value) return
  if (!draft.value.description.trim()) {
    ui.toast(copy.profile.suggestNeedsText, 'warning')
    return
  }
  suggesting.value = true
  try {
    const { keywords } = await profilesApi.suggest(draft.value.description)
    draft.value.keywords = [...new Set([...draft.value.keywords, ...keywords])].slice(0, 10)
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  } finally {
    suggesting.value = false
  }
}

async function save() {
  if (!draft.value) return
  chips.value?.commit()
  saving.value = true
  const d = draft.value
  const body = { name: d.name, description: d.description, keywords: d.keywords, is_default: d.is_default }
  try {
    if (d.id) await profilesApi.update(d.id, body)
    else await profilesApi.create(body)
    ui.toast(copy.profile.saved, 'success')
    draft.value = null
    await queryClient.invalidateQueries({ queryKey: ['profiles'] })
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  } finally {
    saving.value = false
  }
}

async function confirmRemove() {
  if (!removing.value) return
  try {
    await profilesApi.remove(removing.value.id)
    ui.toast(copy.profile.removed, 'success')
    removing.value = null
    await queryClient.invalidateQueries({ queryKey: ['profiles'] })
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  }
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <SubNav :label="copy.nav.settingsLabel" :items="SETTINGS_NAV" />
    <div>
      <UiButton v-if="!draft" @click="startNew">{{ copy.profile.newProfile }}</UiButton>
    </div>

    <form
      v-if="draft"
      class="flex flex-col gap-4 rounded-card border border-border bg-surface p-4"
      @submit.prevent="save"
    >
      <UiInput v-model="draft.name" :label="copy.profile.name" :max-length="50" required />
      <UiTextarea
        v-model="draft.description"
        :label="copy.profile.description"
        :placeholder="copy.profile.descriptionPlaceholder"
        :max-length="4000"
        :rows="6"
      />
      <p v-if="descriptionChanged" class="text-sm text-warning-fg" role="status">{{ copy.profile.changed }}</p>
      <ChipInput ref="chips" v-model="draft.keywords" :label="copy.profile.keywords" :hint="copy.profile.keywordsHint" />
      <div>
        <UiButton variant="secondary" size="sm" :loading="suggesting" @click="suggest">{{ copy.profile.suggest }}</UiButton>
      </div>
      <label class="inline-flex items-center gap-2 text-base">
        <input v-model="draft.is_default" type="checkbox" class="size-4" />
        {{ copy.profile.isDefault }}
      </label>
      <div class="flex gap-2">
        <UiButton type="submit" :loading="saving" :disabled="!draft.name.trim()">{{ copy.common.save }}</UiButton>
        <UiButton variant="ghost" @click="draft = null">{{ copy.common.cancel }}</UiButton>
      </div>
    </form>

    <UiSkeleton v-if="profiles.isPending.value" :lines="2" />
    <EmptyState v-else-if="!profiles.data.value?.items.length && !draft" :title="copy.profile.empty" />
    <ul v-else-if="profiles.data.value?.items.length" class="divide-y divide-border rounded-card border border-border bg-surface">
      <li v-for="p in profiles.data.value.items" :key="p.id" class="flex flex-wrap items-center gap-3 px-4 py-3">
        <span class="text-base font-medium">{{ p.name }}</span>
        <UiBadge v-if="p.is_default" tone="primary">{{ copy.profile.defaultBadge }}</UiBadge>
        <span class="text-sm text-text-3">{{ copy.profile.updated(formatDateTime(p.updated_at)) }}</span>
        <div class="ml-auto flex gap-1">
          <UiButton size="sm" variant="secondary" @click="startEdit(p)">{{ copy.profile.edit }}</UiButton>
          <UiButton size="sm" variant="ghost" @click="removing = p">{{ copy.common.remove }}</UiButton>
        </div>
      </li>
    </ul>

    <UiModal
      :open="removing !== null"
      :title="copy.profile.removeTitle"
      :description="removing ? copy.profile.removeBody(removing.name) : ''"
      @update:open="(v) => !v && (removing = null)"
    >
      <template #actions>
        <UiButton variant="ghost" @click="removing = null">{{ copy.common.cancel }}</UiButton>
        <UiButton variant="danger" @click="confirmRemove">{{ copy.common.confirm }}</UiButton>
      </template>
    </UiModal>
  </div>
</template>

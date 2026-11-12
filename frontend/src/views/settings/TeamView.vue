<script setup lang="ts">
// 팀 설정 (SPEC §13 P6). 팀이 없으면 만들기·코드로 들어가기. 있으면 초대 링크, 팀원, 나가기.
// 팀장만 이름 변경·코드 재발급·내보내기. 한 계정은 한 팀.
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { Copy, Crown, RefreshCw, UserMinus } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { authApi } from '@/api/auth'
import { inviteLink, teamsApi, type MyTeam, type TeamMember } from '@/api/teams'
import SubNav from '@/components/layout/SubNav.vue'
import { SETTINGS_NAV } from '@/components/layout/subnavs'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiModal from '@/components/ui/UiModal.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { copy } from '@/copy'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { generalMessage } from '@/utils/authErrors'
import { formatDateTime } from '@/utils/format'

const auth = useAuthStore()
const ui = useUiStore()
const queryClient = useQueryClient()
const q = useQuery({ queryKey: ['team'], queryFn: () => teamsApi.me() })
const data = computed(() => q.data.value)
const isOwner = computed(() => data.value?.role === 'owner')
const link = computed(() => (data.value?.team ? inviteLink(data.value.team.invite_code) : ''))

const newName = ref('')
const code = ref('')
const rename = ref('')
const busy = ref<string | null>(null)
const leaving = ref(false)
watch(
  () => data.value?.team?.name,
  (n) => (rename.value = n ?? ''),
  { immediate: true },
)

async function run(key: string, fn: () => Promise<MyTeam | void>, done?: string) {
  busy.value = key
  try {
    const res = await fn()
    if (res) queryClient.setQueryData(['team'], res)
    else await q.refetch()
    auth.me = await authApi.me()
    void queryClient.invalidateQueries({ queryKey: ['profiles'] })
    if (done) ui.toast(done, 'success')
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  } finally {
    busy.value = null
  }
}

const create = () => run('create', () => teamsApi.create(newName.value.trim()), copy.team.created)
const join = () => run('join', () => teamsApi.join(code.value.trim()), copy.team.joined)
const saveName = () => run('rename', () => teamsApi.rename(rename.value.trim()), copy.team.renamed)
const rotate = () => run('rotate', () => teamsApi.rotateCode(), copy.team.rotated)
const remove = (m: TeamMember) => run(`remove-${m.user_id}`, () => teamsApi.remove(m.user_id), copy.team.removed)
async function leave() {
  leaving.value = false
  await run('leave', () => teamsApi.leave(), copy.team.left)
}

async function copyLink() {
  try {
    await navigator.clipboard.writeText(link.value)
    ui.toast(copy.team.copied, 'success')
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  }
}
const nameOf = (m: TeamMember) => m.display_name || copy.team.noName
</script>

<template>
  <div class="flex flex-col gap-6">
    <SubNav :label="copy.nav.settingsLabel" :items="SETTINGS_NAV" />

    <UiSkeleton v-if="q.isPending.value" class="h-40" />

    <template v-else-if="data && !data.team">
      <div>
        <p class="text-md font-medium text-text">{{ copy.team.none }}</p>
        <p class="text-base text-text-2">{{ copy.team.noneLead }}</p>
      </div>
      <div class="grid gap-4 md:grid-cols-2">
        <form class="flex flex-col gap-3 rounded-card border border-border bg-surface p-5" @submit.prevent="create">
          <h3 class="text-lg font-semibold">{{ copy.team.createTitle }}</h3>
          <UiInput v-model="newName" :label="copy.team.nameLabel" :max-length="50" required />
          <UiButton type="submit" :disabled="!newName.trim()" :loading="busy === 'create'">
            {{ copy.team.create }}
          </UiButton>
        </form>
        <form class="flex flex-col gap-3 rounded-card border border-border bg-surface p-5" @submit.prevent="join">
          <h3 class="text-lg font-semibold">{{ copy.team.joinTitle }}</h3>
          <UiInput v-model="code" :label="copy.team.codeLabel" :max-length="32" required />
          <UiButton type="submit" variant="secondary" :disabled="!code.trim()" :loading="busy === 'join'">
            {{ copy.team.joinSubmit }}
          </UiButton>
        </form>
      </div>
    </template>

    <template v-else-if="data?.team">
      <section class="flex flex-col gap-3 rounded-card border border-border bg-surface p-5">
        <form v-if="isOwner" class="flex flex-wrap items-end gap-2" @submit.prevent="saveName">
          <div class="min-w-48 flex-1">
            <UiInput v-model="rename" :label="copy.team.nameLabel" :max-length="50" />
          </div>
          <UiButton type="submit" variant="secondary" :disabled="!rename.trim() || rename.trim() === data.team.name" :loading="busy === 'rename'">
            {{ copy.team.rename }}
          </UiButton>
        </form>
        <h3 v-else class="text-xl font-semibold text-text">{{ data.team.name }}</h3>
      </section>

      <section class="flex flex-col gap-3 rounded-card border border-border bg-surface p-5">
        <h3 class="text-lg font-semibold">{{ copy.team.inviteTitle }}</h3>
        <div class="flex flex-col gap-1">
          <span class="text-sm text-text-3">{{ copy.team.inviteLink }}</span>
          <div class="flex flex-wrap items-center gap-2">
            <code class="min-w-0 flex-1 break-all rounded-control bg-surface-2 px-3 py-2 text-sm text-text">{{ link }}</code>
            <UiButton variant="secondary" @click="copyLink">
              <Copy class="size-4" aria-hidden="true" />{{ copy.team.copyLink }}
            </UiButton>
          </div>
        </div>
        <p class="text-sm text-text-2">
          {{ copy.team.inviteCode }} <span class="font-medium tabular tracking-wider text-text">{{ data.team.invite_code }}</span>
        </p>
        <div v-if="isOwner">
          <UiButton variant="ghost" size="sm" :loading="busy === 'rotate'" @click="rotate">
            <RefreshCw class="size-4" aria-hidden="true" />{{ copy.team.rotate }}
          </UiButton>
        </div>
      </section>

      <section class="flex flex-col gap-3 rounded-card border border-border bg-surface p-5">
        <h3 class="text-lg font-semibold">{{ copy.team.members(data.members.length) }}</h3>
        <ul class="divide-y divide-border">
          <li v-for="m in data.members" :key="m.user_id" class="flex flex-wrap items-center gap-3 py-2.5">
            <span class="inline-flex items-center gap-1.5 text-base text-text">
              <Crown v-if="m.role === 'owner'" class="size-4 text-warning-fg" aria-hidden="true" />{{ nameOf(m) }}
            </span>
            <UiBadge :tone="m.role === 'owner' ? 'warning' : 'neutral'">
              {{ m.role === 'owner' ? copy.team.owner : copy.team.member }}
            </UiBadge>
            <span v-if="m.joined_at" class="text-sm text-text-3 tabular">{{ formatDateTime(m.joined_at) }}</span>
            <button
              v-if="isOwner && m.role !== 'owner'"
              type="button"
              class="ml-auto inline-flex size-10 items-center justify-center rounded-control text-text-2 hover:bg-danger-bg hover:text-danger-fg"
              :aria-label="copy.team.remove(nameOf(m))"
              :disabled="busy === `remove-${m.user_id}`"
              @click="remove(m)"
            >
              <UserMinus class="size-4" aria-hidden="true" />
            </button>
          </li>
        </ul>
      </section>

      <div>
        <UiButton variant="danger" :loading="busy === 'leave'" @click="leaving = true">{{ copy.team.leave }}</UiButton>
      </div>
      <UiModal v-model:open="leaving" :title="copy.team.leave" :description="copy.team.leaveConfirm">
        <template #actions>
          <UiButton variant="ghost" @click="leaving = false">{{ copy.common.cancel }}</UiButton>
          <UiButton variant="danger" @click="leave">{{ copy.common.confirm }}</UiButton>
        </template>
      </UiModal>
    </template>
  </div>
</template>

<script setup lang="ts">
// 관리자 사용자 관리 (SPEC §7.9). 상태 탭은 URL 쿼리(?tab=)와 동기화, 변경은 확인 모달을 거친다.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { adminApi, type AdminUser, type UserStatus } from '@/api/auth'
import SubNav from '@/components/layout/SubNav.vue'
import { ADMIN_NAV } from '@/components/layout/subnavs'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiModal from '@/components/ui/UiModal.vue'
import UiTabs from '@/components/ui/UiTabs.vue'
import { copy } from '@/copy'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { generalMessage } from '@/utils/authErrors'
import { formatDateTime } from '@/utils/format'

type Action = 'approve' | 'disable' | 'enable' | 'makeAdmin' | 'makeMember'

const TABS: Array<{ value: UserStatus; label: string }> = [
  { value: 'pending_approval', label: copy.admin.tabPending },
  { value: 'active', label: copy.admin.tabActive },
  { value: 'disabled', label: copy.admin.tabDisabled },
  { value: 'pending_verification', label: copy.admin.tabUnverified },
]

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()

const tab = computed<UserStatus>({
  get: () => TABS.find((t) => t.value === route.query.tab)?.value ?? 'pending_approval',
  set: (v) => void router.replace({ query: { ...route.query, tab: v } }),
})
const users = ref<AdminUser[]>([])
const total = ref(0)
const loading = ref(false)
const pending = ref<{ user: AdminUser; action: Action } | null>(null)
const saving = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await adminApi.users(tab.value)
    users.value = res.items
    total.value = res.total
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  } finally {
    loading.value = false
  }
}
watch(tab, load, { immediate: true })

function actionsFor(u: AdminUser): Action[] {
  if (u.id === auth.me?.id) return []
  const list: Action[] = []
  if (u.status === 'pending_approval' || u.status === 'pending_verification') list.push('approve')
  if (u.status === 'active') list.push('disable', u.role === 'admin' ? 'makeMember' : 'makeAdmin')
  if (u.status === 'disabled') list.push('enable')
  return list
}

const LABELS: Record<Action, string> = {
  approve: copy.admin.approve,
  disable: copy.admin.disable,
  enable: copy.admin.enable,
  makeAdmin: copy.admin.makeAdmin,
  makeMember: copy.admin.makeMember,
}

const confirmText = computed(() => {
  if (!pending.value) return ''
  const e = pending.value.user.email
  return {
    approve: copy.admin.confirmApprove(e),
    disable: copy.admin.confirmDisable(e),
    enable: copy.admin.confirmEnable(e),
    makeAdmin: copy.admin.confirmMakeAdmin(e),
    makeMember: copy.admin.confirmMakeMember(e),
  }[pending.value.action]
})

const modalOpen = computed({
  get: () => pending.value !== null,
  set: (v) => {
    if (!v) pending.value = null
  },
})

async function apply() {
  if (!pending.value) return
  const { user, action } = pending.value
  const patch = {
    approve: { status: 'active' as const },
    enable: { status: 'active' as const },
    disable: { status: 'disabled' as const },
    makeAdmin: { role: 'admin' as const },
    makeMember: { role: 'member' as const },
  }[action]
  saving.value = true
  try {
    await adminApi.update(user.id, patch)
    ui.toast(copy.admin.done, 'success')
    pending.value = null
    await load()
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="flex flex-col gap-4">
    <SubNav :label="copy.nav.adminLabel" :items="ADMIN_NAV" />
    <UiTabs v-model="tab" :items="TABS" :label="copy.admin.tabsLabel" />
    <p class="text-sm text-text-3 tabular" aria-live="polite">{{ copy.admin.total(total) }}</p>

    <div class="overflow-hidden rounded-card border border-border bg-surface">
      <EmptyState v-if="!loading && users.length === 0" :title="copy.admin.empty" />
      <table v-else class="w-full text-left text-sm">
        <thead class="hidden bg-surface-2 text-text-2 md:table-header-group">
          <tr>
            <th scope="col" class="px-4 py-2 font-medium">{{ copy.admin.colEmail }}</th>
            <th scope="col" class="px-4 py-2 font-medium">{{ copy.admin.colName }}</th>
            <th scope="col" class="px-4 py-2 font-medium">{{ copy.admin.colRole }}</th>
            <th scope="col" class="px-4 py-2 font-medium">{{ copy.admin.colCreated }}</th>
            <th scope="col" class="px-4 py-2 font-medium">{{ copy.admin.colLastLogin }}</th>
            <th scope="col" class="px-4 py-2 font-medium">{{ copy.admin.colActions }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="u in users"
            :key="u.id"
            class="flex flex-col gap-1 border-t border-border px-4 py-3 first:border-t-0 md:table-row md:px-0 md:py-0"
          >
            <td class="font-medium text-text md:px-4 md:py-3">
              {{ u.email }}
              <UiBadge v-if="u.id === auth.me?.id" tone="primary" class="ml-1">{{ copy.admin.me }}</UiBadge>
            </td>
            <td class="text-text-2 md:px-4 md:py-3">{{ u.display_name }}</td>
            <td class="md:px-4 md:py-3">
              <UiBadge :tone="u.role === 'admin' ? 'primary' : 'neutral'">
                {{ u.role === 'admin' ? copy.nav.roleAdmin : copy.nav.roleMember }}
              </UiBadge>
            </td>
            <td class="text-text-3 tabular md:px-4 md:py-3">
              <span class="mr-2 md:hidden">{{ copy.admin.colCreated }}</span>{{ formatDateTime(u.created_at) }}
            </td>
            <td class="text-text-3 tabular md:px-4 md:py-3">
              <span class="mr-2 md:hidden">{{ copy.admin.colLastLogin }}</span>
              {{ u.last_login_at ? formatDateTime(u.last_login_at) : copy.admin.never }}
            </td>
            <td class="md:px-4 md:py-3">
              <div class="flex flex-wrap gap-2">
                <UiButton
                  v-for="a in actionsFor(u)"
                  :key="a"
                  size="sm"
                  :variant="a === 'disable' ? 'danger' : a === 'approve' ? 'primary' : 'secondary'"
                  @click="pending = { user: u, action: a }"
                >{{ LABELS[a] }}</UiButton>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <UiModal v-model:open="modalOpen" :title="copy.admin.confirmTitle" :description="confirmText">
      <template #actions>
        <UiButton variant="secondary" @click="pending = null">{{ copy.common.cancel }}</UiButton>
        <UiButton
          :variant="pending?.action === 'disable' ? 'danger' : 'primary'"
          :loading="saving"
          @click="apply"
        >{{ copy.common.confirm }}</UiButton>
      </template>
    </UiModal>
  </section>
</template>

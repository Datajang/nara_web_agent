<script setup lang="ts">
// 관리자 수집기 (SPEC §7.9): 소스별 수집 범위, 최근 실행 20건, 수동 실행(확인 모달 후).
import { useQuery } from '@tanstack/vue-query'
import { computed, ref } from 'vue'
import { opsApi } from '@/api/admin'
import type { CollectorRunIn } from '@/api/types'
import SubNav from '@/components/layout/SubNav.vue'
import { ADMIN_NAV } from '@/components/layout/subnavs'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiModal from '@/components/ui/UiModal.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { copy } from '@/copy'
import { useUiStore } from '@/stores/ui'
import { generalMessage } from '@/utils/authErrors'
import { formatDateTime } from '@/utils/format'

const ui = useUiStore()
const runs = useQuery({ queryKey: ['collector-runs'], queryFn: () => opsApi.collectorRuns(20) })
const form = ref<{ mode: 'incremental' | 'backfill'; source: 'regular' | 'prespec'; days: string }>({
  mode: 'incremental',
  source: 'regular',
  days: '7',
})
const confirming = ref(false)
const running = ref(false)
const statusTone = { running: 'warning', ok: 'success', failed: 'danger' } as const
const label = (map: Record<string, string>, k: string) => map[k] ?? k
const description = computed(
  () => `${copy.admin.sources[form.value.source]} · ${copy.admin.modes[form.value.mode]}`,
)

async function run() {
  running.value = true
  const days = Math.min(90, Math.max(1, Number(form.value.days) || 7))
  const body: CollectorRunIn = { mode: form.value.mode, source: form.value.source, days }
  try {
    await opsApi.runCollector(body)
    confirming.value = false
    ui.toast(copy.admin.runStarted, 'success')
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  } finally {
    running.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <SubNav :label="copy.nav.adminLabel" :items="ADMIN_NAV" />
    <UiSkeleton v-if="runs.isPending.value" :lines="2" />
    <template v-else-if="runs.data.value">
      <section class="rounded-card border border-border bg-surface p-4">
        <h3 class="mb-3 text-lg font-semibold">{{ copy.admin.coverage }}</h3>
        <p v-if="!runs.data.value.coverage.length" class="text-text-3">{{ copy.admin.noCoverage }}</p>
        <ul v-else class="flex flex-col gap-1">
          <li v-for="c in runs.data.value.coverage" :key="c.source" class="flex flex-wrap gap-3 text-base">
            <span class="font-medium">{{ label(copy.admin.sources, c.source) }}</span>
            <span class="tabular text-text-2">{{ formatDateTime(c.covered_from) }} ~ {{ formatDateTime(c.covered_to) }}</span>
          </li>
        </ul>
      </section>

      <section class="rounded-card border border-border bg-surface p-4">
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-lg font-semibold">{{ copy.admin.recentRuns }}</h3>
          <UiButton size="sm" variant="ghost" @click="runs.refetch()">{{ copy.common.refresh }}</UiButton>
        </div>
        <p v-if="!runs.data.value.items.length" class="text-text-3">{{ copy.admin.noRuns }}</p>
        <div v-else class="overflow-x-auto">
          <table class="w-full min-w-[640px] text-sm">
            <thead class="bg-surface-2 text-left text-text-2">
              <tr>
                <th scope="col" class="px-3 py-2">{{ copy.admin.colStarted }}</th>
                <th scope="col" class="px-3 py-2">{{ copy.admin.colSource }}</th>
                <th scope="col" class="px-3 py-2">{{ copy.admin.colMode }}</th>
                <th scope="col" class="px-3 py-2">{{ copy.admin.colStatus }}</th>
                <th scope="col" class="px-3 py-2 text-right">{{ copy.admin.colFetched }}</th>
                <th scope="col" class="px-3 py-2 text-right">{{ copy.admin.colInserted }}</th>
                <th scope="col" class="px-3 py-2 text-right">{{ copy.admin.colUpdated }}</th>
                <th scope="col" class="px-3 py-2">{{ copy.admin.colError }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in runs.data.value.items" :key="r.id" class="border-t border-border">
                <td class="px-3 py-2 tabular">{{ formatDateTime(r.started_at) }}</td>
                <td class="px-3 py-2">{{ label(copy.admin.sources, r.source) }}</td>
                <td class="px-3 py-2">{{ label(copy.admin.modes, r.mode) }}</td>
                <td class="px-3 py-2">
                  <UiBadge :tone="statusTone[r.status as keyof typeof statusTone] ?? 'neutral'">
                    {{ label(copy.admin.runStatus, r.status) }}
                  </UiBadge>
                </td>
                <td class="px-3 py-2 text-right tabular">{{ r.fetched }}</td>
                <td class="px-3 py-2 text-right tabular">{{ r.inserted }}</td>
                <td class="px-3 py-2 text-right tabular">{{ r.updated }}</td>
                <td class="max-w-48 truncate px-3 py-2 text-text-2" :title="r.error ?? undefined">{{ r.error }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>

    <form
      class="flex flex-wrap items-end gap-3 rounded-card border border-border bg-surface p-4"
      :aria-label="copy.admin.runForm"
      @submit.prevent="confirming = true"
    >
      <h3 class="w-full text-lg font-semibold">{{ copy.admin.runForm }}</h3>
      <div class="w-40">
        <UiSelect
          v-model="form.mode"
          :label="copy.admin.mode"
          :options="[
            { value: 'incremental', label: copy.admin.modes.incremental },
            { value: 'backfill', label: copy.admin.modes.backfill },
          ]"
        />
      </div>
      <div class="w-40">
        <UiSelect
          v-model="form.source"
          :label="copy.admin.colSource"
          :options="[
            { value: 'regular', label: copy.admin.sources.regular },
            { value: 'prespec', label: copy.admin.sources.prespec },
          ]"
        />
      </div>
      <div v-if="form.mode === 'backfill'" class="w-28">
        <UiInput v-model="form.days" type="number" :label="copy.admin.days" />
      </div>
      <UiButton type="submit">{{ copy.admin.runSubmit }}</UiButton>
    </form>

    <UiModal v-model:open="confirming" :title="copy.admin.confirmTitle" :description="copy.admin.confirmRun(description)">
      <template #actions>
        <UiButton variant="ghost" @click="confirming = false">{{ copy.common.cancel }}</UiButton>
        <UiButton :loading="running" @click="run">{{ copy.common.confirm }}</UiButton>
      </template>
    </UiModal>
  </div>
</template>

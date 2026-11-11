<script setup lang="ts">
// 관리자 사용량 (SPEC §7.9, §5.8): 기간 선택 → 지표 카드(G2B 호출, LLM 입력·출력 토큰, 계층별 적중률)와 일별 추이.
import { useQuery } from '@tanstack/vue-query'
import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'
import { computed, ref } from 'vue'
import { Line } from 'vue-chartjs'
import { opsApi } from '@/api/admin'
import type { UsageRow } from '@/api/types'
import SubNav from '@/components/layout/SubNav.vue'
import { ADMIN_NAV } from '@/components/layout/subnavs'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { copy } from '@/copy'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend)

const LAYERS = ['bids_db', 'file_text', 'summary', 'analysis', 'score'] as const
const kstDate = (d: Date) => new Date(d.getTime() + 9 * 3_600_000).toISOString().slice(0, 10)
const from = ref(kstDate(new Date(Date.now() - 13 * 86_400_000)))
const to = ref(kstDate(new Date()))
const applied = ref({ from: from.value, to: to.value })

const usage = useQuery({
  queryKey: computed(() => ['admin-usage', applied.value.from, applied.value.to]),
  queryFn: () => opsApi.usage(applied.value.from, applied.value.to),
})
const rows = computed<UsageRow[]>(() => usage.data.value?.items ?? [])
const sum = (k: 'requests' | 'g2b_calls' | 'llm_calls' | 'prompt_tokens' | 'completion_tokens') =>
  rows.value.reduce((n, r) => n + r[k], 0)
const fmt = (n: number) => n.toLocaleString('ko-KR')

const totals = computed(() => [
  { label: copy.admin.requests, value: fmt(sum('requests')) },
  { label: copy.admin.g2bCalls, value: fmt(sum('g2b_calls')) },
  { label: copy.admin.llmCalls, value: fmt(sum('llm_calls')) },
  { label: copy.admin.promptTokens, value: fmt(sum('prompt_tokens')) },
  { label: copy.admin.completionTokens, value: fmt(sum('completion_tokens')) },
])

/** 계층별 적중률: 그 계층을 기록한 행만 요청 수로 가중 평균. */
const hitRates = computed(() =>
  LAYERS.map((layer) => {
    const seen = rows.value.filter((r) => r.hit_rate[layer] != null)
    const weight = seen.reduce((n, r) => n + r.requests, 0)
    const rate = weight ? seen.reduce((n, r) => n + (r.hit_rate[layer] ?? 0) * r.requests, 0) / weight : null
    return { label: copy.admin.layers[layer], value: rate === null ? copy.admin.noHits : `${Math.round(rate * 100)}%` }
  }),
)

const chart = computed(() => {
  const days = [...new Set(rows.value.map((r) => r.day))].sort()
  const byDay = (k: 'g2b_calls' | 'llm_calls') =>
    days.map((d) => rows.value.filter((r) => r.day === d).reduce((n, r) => n + r[k], 0))
  return {
    labels: days,
    datasets: [
      { label: copy.admin.g2bCalls, data: byDay('g2b_calls'), borderColor: '#2F5BEA', backgroundColor: '#2F5BEA' },
      { label: copy.admin.llmCalls, data: byDay('llm_calls'), borderColor: '#B54708', backgroundColor: '#B54708' },
    ],
  }
})
</script>

<template>
  <div class="flex flex-col gap-4">
    <SubNav :label="copy.nav.adminLabel" :items="ADMIN_NAV" />
    <form class="flex flex-wrap items-end gap-3" @submit.prevent="applied = { from, to }">
      <UiInput v-model="from" type="date" :label="copy.admin.from" />
      <UiInput v-model="to" type="date" :label="copy.admin.to" />
      <UiButton type="submit" variant="secondary">{{ copy.admin.apply }}</UiButton>
    </form>
    <UiSkeleton v-if="usage.isPending.value" :lines="2" />
    <EmptyState v-else-if="!rows.length" :title="copy.admin.noUsage" />
    <template v-else>
      <dl class="grid grid-cols-2 gap-3 md:grid-cols-5">
        <div v-for="t in totals" :key="t.label" class="rounded-card border border-border bg-surface p-4">
          <dt class="text-sm text-text-2">{{ t.label }}</dt>
          <dd class="text-xl font-semibold tabular">{{ t.value }}</dd>
        </div>
      </dl>
      <section class="rounded-card border border-border bg-surface p-4">
        <h3 class="mb-3 text-lg font-semibold">{{ copy.admin.hitRate }}</h3>
        <dl class="grid grid-cols-2 gap-3 md:grid-cols-5">
          <div v-for="h in hitRates" :key="h.label">
            <dt class="text-sm text-text-2">{{ h.label }}</dt>
            <dd class="text-lg font-semibold tabular">{{ h.value }}</dd>
          </div>
        </dl>
      </section>
      <section class="rounded-card border border-border bg-surface p-4">
        <h3 class="mb-3 text-lg font-semibold">{{ copy.admin.daily }}</h3>
        <div class="h-64"><Line :data="chart" :options="{ responsive: true, maintainAspectRatio: false }" /></div>
      </section>
    </template>
  </div>
</template>

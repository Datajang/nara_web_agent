<script setup lang="ts">
// 낙찰 요약 (§15.7): 요약 카드 4개, 연도별 막대, 수요기관별, 분야 태그.
// 연도별은 한 계열이라 범례 없이 값을 옆에 적고, 수집 중인 해는 막대 대신 '수집 중' 글자를 쓴다(dataviz).
import { computed } from 'vue'
import type { AwardSummary } from '@/api/awards'
import MoneyText from '@/components/bid/MoneyText.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'
import { formatMoney } from '@/utils/format'

const props = defineProps<{ summary: AwardSummary; field?: string; org?: string }>()
const emit = defineEmits<{ 'update:field': [string]; 'update:org': [string] }>()

const maxYear = computed(() => Math.max(1, ...props.summary.by_year.map((y) => y.count ?? 0)))
const years = computed(() => [...props.summary.by_year].reverse()) // 최근 해가 위
</script>

<template>
  <div class="flex flex-col gap-4">
    <!-- 요약 숫자 띠 (2026-11-18 시안 D): 카드 하나를 칸으로 나눈다(1px 간격이 구분선) -->
    <dl class="grid grid-cols-2 gap-px overflow-hidden rounded-card border border-border bg-border lg:grid-cols-4" data-summary-cards>
      <div class="bg-surface px-5 py-4">
        <dt class="text-xs text-text-3">{{ copy.awards.count }}</dt>
        <dd class="mt-1 text-2xl font-semibold tabular">{{ copy.awards.countUnit(summary.count) }}</dd>
      </div>
      <div class="bg-surface px-5 py-4">
        <dt class="text-xs text-text-3">{{ copy.awards.amountSum }}</dt>
        <dd class="mt-1 text-2xl font-semibold"><MoneyText :value="summary.amount_sum" /></dd>
      </div>
      <div class="bg-surface px-5 py-4">
        <dt class="text-xs text-text-3">{{ copy.awards.amountAvg }}</dt>
        <dd class="mt-1 text-2xl font-semibold"><MoneyText :value="summary.amount_avg" /></dd>
      </div>
      <div class="bg-surface px-5 py-4">
        <dt class="text-xs text-text-3">{{ copy.awards.orgCount }}</dt>
        <dd class="mt-1 text-2xl font-semibold tabular">{{ copy.awards.orgUnit(summary.org_count) }}</dd>
      </div>
    </dl>

    <div class="grid gap-4 lg:grid-cols-2">
      <section class="rounded-card border border-border bg-surface p-4" :aria-label="copy.awards.byYear">
        <h3 class="mb-3 text-lg font-semibold">{{ copy.awards.byYear }}</h3>
        <ul class="flex flex-col gap-2">
          <li
            v-for="y in years"
            :key="y.year"
            class="grid grid-cols-[4rem_1fr_auto] items-center gap-3 text-sm"
            :data-year="y.year"
          >
            <span class="tabular text-text-2">{{ copy.awards.yearLabel(y.year) }}</span>
            <span class="h-3 rounded-sm bg-surface-2">
              <span
                v-if="y.count"
                class="block h-3 rounded-r-[4px] bg-primary"
                :style="{ width: `${(y.count / maxYear) * 100}%` }"
                :title="copy.awards.yearTooltip(y.year, y.count, formatMoney(y.amount_sum))"
              />
            </span>
            <span class="flex items-center gap-1.5 tabular">
              <template v-if="y.count !== null">{{ copy.awards.countUnit(y.count) }}</template>
              <UiBadge v-if="y.collecting" tone="warning">{{ copy.awards.collecting }}</UiBadge>
            </span>
          </li>
        </ul>
      </section>

      <section class="rounded-card border border-border bg-surface p-4" :aria-label="copy.awards.byOrg">
        <h3 class="mb-3 text-lg font-semibold">{{ copy.awards.byOrg }}</h3>
        <p v-if="!summary.by_org.length" class="text-text-3">{{ copy.awards.noOrgs }}</p>
        <ul v-else class="flex flex-col divide-y divide-border">
          <li v-for="o in summary.by_org" :key="o.dminstt_cd ?? ''">
            <button
              type="button"
              class="flex w-full items-center gap-3 py-2 text-left text-sm hover:bg-surface-2"
              :aria-pressed="org === o.dminstt_cd"
              :class="org === o.dminstt_cd ? 'font-semibold text-primary-hover' : ''"
              @click="emit('update:org', org === o.dminstt_cd ? '' : (o.dminstt_cd ?? ''))"
            >
              <span class="min-w-0 flex-1 truncate">{{ o.dminstt_name ?? o.dminstt_cd }}</span>
              <span class="tabular text-text-2">{{ copy.awards.countUnit(o.count) }}</span>
              <MoneyText :value="o.amount_sum" class="w-20 text-right text-text-2" />
            </button>
          </li>
        </ul>
      </section>
    </div>

    <section class="rounded-card border border-border bg-surface p-4" :aria-label="copy.awards.byField">
      <h3 class="mb-3 text-lg font-semibold">{{ copy.awards.byField }}</h3>
      <p v-if="!summary.by_field.length" class="text-text-3">{{ copy.awards.noFields }}</p>
      <div v-else class="flex flex-wrap gap-2">
        <button
          v-for="f in summary.by_field"
          :key="f.field"
          type="button"
          class="inline-flex h-8 items-center gap-2 rounded-tag border px-3 text-sm"
          :class="field === f.field ? 'border-primary bg-primary-soft text-primary-hover' : 'border-border bg-surface'"
          :aria-pressed="field === f.field"
          data-field-chip
          @click="emit('update:field', field === f.field ? '' : f.field)"
        >
          {{ f.field }}<span class="tabular text-text-2">{{ copy.awards.countUnit(f.count) }}</span>
        </button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
// 요약 카드의 구조화 정보 (SPEC §7.5-3). 내용마다 다른 모양으로 나눠 한눈에 훑게 한다.
// 핵심 숫자 줄(예산·계약 방법·기간) → 일정 타임라인 | 배점 막대 → 참가 자격 체크 목록 → 핵심 요구사항(5개 + 접기).
// 비어 있는 항목은 제목째 숨긴다.
import { BadgeCheck, CalendarDays, CircleCheck, ListChecks, Scale } from 'lucide-vue-next'
import { computed } from 'vue'
import type { BidSummary } from '@/api/types'
import { copy } from '@/copy'
import EvaluationBars from './EvaluationBars.vue'
import RequirementList from './RequirementList.vue'
import ScheduleTimeline from './ScheduleTimeline.vue'

const props = defineProps<{ summary: BidSummary }>()
const SHOWN = 5

const strip = computed(() => {
  const b = props.summary.budget_contract
  const rows: [string, string | null | undefined][] = [
    [copy.analysis.budgetText, b.budget_text],
    [copy.analysis.contractMethod, b.contract_method],
    [copy.analysis.period, b.period],
  ]
  return rows.filter((r): r is [string, string] => !!r[1])
})
const payment = computed(() => props.summary.budget_contract.payment_terms)
const evaluation = computed(() => props.summary.evaluation)
const hasEvaluation = computed(() => !!evaluation.value.method || !!evaluation.value.items?.length)
const reqs = computed(() => props.summary.key_requirements)
const hasBudget = computed(() => strip.value.length > 0 || !!payment.value)
const any = computed(
  () =>
    hasBudget.value ||
    props.summary.schedule.length > 0 ||
    hasEvaluation.value ||
    props.summary.eligibility.length > 0 ||
    reqs.value.length > 0,
)
const stripCols = { 1: 'sm:grid-cols-1', 2: 'sm:grid-cols-2', 3: 'sm:grid-cols-3' } as Record<number, string>
</script>

<template>
  <div v-if="any" class="mt-5 flex flex-col gap-6">
    <section v-if="hasBudget">
      <h4 class="sr-only">{{ copy.analysis.budget }}</h4>
      <dl
        v-if="strip.length"
        class="grid divide-y divide-border rounded-card bg-surface-2 sm:divide-x sm:divide-y-0"
        :class="stripCols[strip.length]"
      >
        <div v-for="[label, value] in strip" :key="label" class="min-w-0 px-4 py-3">
          <dt class="text-sm text-text-3">{{ label }}</dt>
          <dd class="mt-0.5 text-md font-medium tabular text-text">{{ value }}</dd>
        </div>
      </dl>
      <p v-if="payment" class="mt-2 text-sm text-text-2">
        <span class="text-text-3">{{ copy.analysis.payment }}</span>&ensp;{{ payment }}
      </p>
    </section>

    <div v-if="summary.schedule.length || hasEvaluation" class="grid items-start gap-4 md:grid-cols-2">
      <section v-if="summary.schedule.length" class="rounded-card border border-border p-4">
        <h4 class="mb-3 flex items-center gap-2 text-base font-semibold text-text">
          <CalendarDays class="size-4 text-primary" aria-hidden="true" />{{ copy.analysis.schedule }}
        </h4>
        <ScheduleTimeline :items="summary.schedule" />
      </section>
      <section v-if="hasEvaluation" class="rounded-card border border-border p-4">
        <h4 class="mb-3 flex items-center gap-2 text-base font-semibold text-text">
          <Scale class="size-4 text-primary" aria-hidden="true" />{{ copy.analysis.evaluation }}
        </h4>
        <EvaluationBars :evaluation="evaluation" />
      </section>
    </div>

    <section v-if="summary.eligibility.length">
      <h4 class="mb-2 flex items-center gap-2 text-base font-semibold text-text">
        <BadgeCheck class="size-4 text-primary" aria-hidden="true" />{{ copy.detail.eligibility }}
      </h4>
      <ul class="grid gap-x-6 gap-y-2 md:grid-cols-2">
        <li v-for="(e, i) in summary.eligibility" :key="i" class="flex items-start gap-2 text-base">
          <CircleCheck class="mt-0.5 size-4 shrink-0 text-success-fg" aria-hidden="true" />
          <span class="min-w-0">{{ e }}</span>
        </li>
      </ul>
    </section>

    <section v-if="reqs.length">
      <h4 class="mb-2 flex items-center gap-2 text-base font-semibold text-text">
        <ListChecks class="size-4 text-primary" aria-hidden="true" />{{ copy.analysis.requirements }}
      </h4>
      <RequirementList :items="reqs.slice(0, SHOWN)" />
      <details v-if="reqs.length > SHOWN" class="group mt-2">
        <summary
          class="inline-flex min-h-10 cursor-pointer items-center rounded-control text-sm font-medium text-primary-hover hover:underline focus-visible:outline-2 focus-visible:outline-primary"
        >{{ copy.detail.moreRequirements(reqs.length - SHOWN) }}</summary>
        <RequirementList class="mt-2" :items="reqs.slice(SHOWN)" />
      </details>
    </section>
  </div>
</template>

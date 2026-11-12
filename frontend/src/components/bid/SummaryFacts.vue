<script setup lang="ts">
// 요약 카드의 구조화 정보 (SPEC §7.5-3): 일정·예산·계약·평가·자격·핵심 요구사항.
// 분석 결과(AnalysisResultView)와 달리 비어 있는 항목은 제목째 숨긴다. 요구사항은 5개까지만 펼친다.
import { computed } from 'vue'
import type { BidSummary } from '@/api/types'
import { copy } from '@/copy'

const props = defineProps<{ summary: BidSummary }>()
const SHOWN = 5

const budgetRows = computed(() => {
  const b = props.summary.budget_contract
  const rows: [string, string | null | undefined][] = [
    [copy.analysis.budgetText, b.budget_text],
    [copy.analysis.contractMethod, b.contract_method],
    [copy.analysis.period, b.period],
    [copy.analysis.payment, b.payment_terms],
  ]
  return rows.filter((r): r is [string, string] => !!r[1])
})
const evaluation = computed(() => props.summary.evaluation)
const hasEvaluation = computed(() => !!evaluation.value.method || !!evaluation.value.items?.length)
const reqs = computed(() => props.summary.key_requirements)
</script>

<template>
  <div
    v-if="summary.schedule.length || budgetRows.length || hasEvaluation || summary.eligibility.length || reqs.length"
    class="mt-4 grid gap-4 border-t border-border pt-4 md:grid-cols-2"
  >
    <section v-if="summary.schedule.length">
      <h4 class="mb-1 text-sm font-semibold text-text-2">{{ copy.analysis.schedule }}</h4>
      <ul class="flex flex-col gap-1 text-base">
        <li v-for="(s, i) in summary.schedule" :key="i" class="flex justify-between gap-4">
          <span>{{ s.label }}</span>
          <span class="tabular shrink-0 text-text-2">{{ s.date || s.raw || '' }}</span>
        </li>
      </ul>
    </section>

    <section v-if="budgetRows.length">
      <h4 class="mb-1 text-sm font-semibold text-text-2">{{ copy.analysis.budget }}</h4>
      <dl class="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-base">
        <template v-for="[label, value] in budgetRows" :key="label">
          <dt class="text-text-2">{{ label }}</dt>
          <dd>{{ value }}</dd>
        </template>
      </dl>
    </section>

    <section v-if="hasEvaluation">
      <h4 class="mb-1 text-sm font-semibold text-text-2">{{ copy.analysis.evaluation }}</h4>
      <p v-if="evaluation.method" class="mb-1 text-base">{{ evaluation.method }}</p>
      <ul v-if="evaluation.items?.length" class="flex flex-col gap-1 text-base">
        <li v-for="(e, i) in evaluation.items" :key="i" class="flex justify-between gap-4">
          <span>{{ e.name }}</span>
          <span v-if="e.points != null" class="tabular shrink-0 text-text-2">{{ copy.analysis.points(e.points) }}</span>
        </li>
      </ul>
    </section>

    <section v-if="summary.eligibility.length">
      <h4 class="mb-1 text-sm font-semibold text-text-2">{{ copy.detail.eligibility }}</h4>
      <ul class="list-disc pl-5 text-base">
        <li v-for="(e, i) in summary.eligibility" :key="i">{{ e }}</li>
      </ul>
    </section>

    <section v-if="reqs.length" class="md:col-span-2">
      <h4 class="mb-1 text-sm font-semibold text-text-2">{{ copy.analysis.requirements }}</h4>
      <ul class="list-disc pl-5 text-base">
        <li v-for="(r, i) in reqs.slice(0, SHOWN)" :key="i">{{ r.text }}</li>
      </ul>
      <details v-if="reqs.length > SHOWN" class="mt-1">
        <summary class="cursor-pointer text-sm text-primary">{{ copy.detail.moreRequirements(reqs.length - SHOWN) }}</summary>
        <ul class="mt-1 list-disc pl-5 text-base">
          <li v-for="(r, i) in reqs.slice(SHOWN)" :key="i">{{ r.text }}</li>
        </ul>
      </details>
    </section>
  </div>
</template>

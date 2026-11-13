<script setup lang="ts">
// G2B 공고 정보 (SPEC §7.5-3, docs/decisions/2026-11-13-official-facts.md).
// 마감·개찰 일시, 예산, 입찰·낙찰 방법은 AI를 거치지 않은 나라장터 값이다. 금액은 원 단위까지 그대로 쓴다
// (줄인 표기는 틀린 값으로 읽힐 수 있다). 비어 있는 값은 줄째 숨기고, 마감만은 '미정'으로 보여 준다.
// 첨부 문서의 사업 금액이 G2B 값과 다르면 아래에 함께 보여 준다(사용자 결정, 어느 쪽인지 고르지 않는다).
import { computed } from 'vue'
import type { BidDetail } from '@/api/types'
import { copy } from '@/copy'
import { formatDateTime } from '@/utils/format'

const props = defineProps<{ facts: BidDetail['official']; docBudgets?: BidDetail['doc_budgets'] }>()
const won = (n: number) => `${n.toLocaleString('ko-KR')}${copy.format.won}`

const rows = computed(() => {
  const f = props.facts
  const out: [string, string][] = [
    [f.deadline_label, f.deadline_at ? formatDateTime(f.deadline_at) : copy.official.none],
  ]
  if (f.opening_at) out.push([copy.official.opening, formatDateTime(f.opening_at)])
  if (f.assigned_budget) out.push([copy.official.assignedBudget, won(f.assigned_budget)])
  if (f.estimated_price) out.push([copy.official.estimatedPrice, won(f.estimated_price)])
  if (f.contract_method) out.push([copy.official.contractMethod, f.contract_method])
  if (f.award_method) out.push([copy.official.awardMethod, f.award_method])
  return out
})
</script>

<template>
  <section data-official class="rounded-card border border-border bg-surface p-4">
    <h3 class="text-lg font-semibold">{{ copy.official.title }}</h3>
    <p class="mb-3 text-sm text-text-3">{{ copy.official.lead }}</p>
    <dl class="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
      <div v-for="[label, value] in rows" :key="label" class="min-w-0">
        <dt class="text-sm text-text-3">{{ label }}</dt>
        <dd class="mt-0.5 text-md font-medium tabular text-text">{{ value }}</dd>
      </div>
    </dl>
    <div v-if="docBudgets?.length" class="mt-4 rounded-control border border-border bg-warning-bg p-3">
      <p class="text-sm font-semibold text-warning-fg">{{ copy.official.docBudgetTitle }}</p>
      <p class="mb-2 text-sm text-text-2">{{ copy.official.docBudgetLead }}</p>
      <ul class="flex flex-col gap-1">
        <li v-for="d in docBudgets" :key="`${d.file}-${d.amount}`" class="flex flex-wrap items-baseline gap-x-2 text-sm">
          <span class="text-md font-medium tabular text-text">{{ won(d.amount) }}</span>
          <span class="min-w-0 break-all text-text-3">{{ d.file }} · {{ d.label }}</span>
        </li>
      </ul>
    </div>
  </section>
</template>

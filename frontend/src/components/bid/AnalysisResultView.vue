<script setup lang="ts">
// 분석 결과 (SPEC §7.5-5). 순서 고정: 개요·요구사항·평가·일정·예산·리스크·적합도·다음 할 일.
import type { AnalysisResult } from '@/api/types'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'
import ScoreBadge from './ScoreBadge.vue'

defineProps<{ analysis: AnalysisResult }>()
const sevTone = { high: 'danger', mid: 'warning', low: 'neutral' } as const
</script>

<template>
  <div class="flex flex-col gap-6">
    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.overview }}</h3>
      <p class="whitespace-pre-line text-base text-text">{{ analysis.overview }}</p>
    </section>

    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.requirements }}</h3>
      <p v-if="!analysis.requirements.length" class="text-text-3">{{ copy.analysis.none }}</p>
      <ul v-else class="flex flex-col gap-2">
        <li v-for="(r, i) in analysis.requirements" :key="i" class="text-base">
          {{ r.text }}
          <span v-if="r.source" class="ml-1 text-sm text-text-3">{{ copy.analysis.source(r.source) }}</span>
          <q v-if="r.evidence" class="mt-1 block text-sm text-text-2">{{ r.evidence }}</q>
        </li>
      </ul>
    </section>

    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.evaluation }}</h3>
      <p v-if="analysis.evaluation.method" class="mb-2 text-sm text-text-2">
        {{ copy.analysis.method }}: {{ analysis.evaluation.method }}
      </p>
      <p v-if="!analysis.evaluation.items?.length" class="text-text-3">{{ copy.analysis.none }}</p>
      <ul v-else class="flex flex-col gap-1">
        <li v-for="(e, i) in analysis.evaluation.items" :key="i" class="flex justify-between gap-4">
          <span>{{ e.name }}<span v-if="e.note" class="text-sm text-text-3"> — {{ e.note }}</span></span>
          <span v-if="e.points != null" class="tabular">{{ copy.analysis.points(e.points) }}</span>
        </li>
      </ul>
    </section>

    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.schedule }}</h3>
      <p v-if="!analysis.schedule.length" class="text-text-3">{{ copy.analysis.none }}</p>
      <ul v-else class="flex flex-col gap-1">
        <li v-for="(s, i) in analysis.schedule" :key="i" class="flex justify-between gap-4">
          <span>{{ s.label }}</span>
          <span class="tabular text-text-2">{{ s.date || s.raw || copy.format.noDeadline }}</span>
        </li>
      </ul>
    </section>

    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.budget }}</h3>
      <dl class="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-base">
        <template
          v-for="[label, value] in [
            [copy.analysis.budgetText, analysis.budget_contract.budget_text],
            [copy.analysis.contractMethod, analysis.budget_contract.contract_method],
            [copy.analysis.payment, analysis.budget_contract.payment_terms],
            [copy.analysis.period, analysis.budget_contract.period],
          ]"
          :key="label"
        >
          <dt class="text-text-2">{{ label }}</dt>
          <dd>{{ value || copy.analysis.none }}</dd>
        </template>
      </dl>
    </section>

    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.risks }}</h3>
      <p v-if="!analysis.risks.length" class="text-text-3">{{ copy.analysis.none }}</p>
      <ul v-else class="flex flex-col gap-2">
        <li v-for="(r, i) in analysis.risks" :key="i" class="flex items-start gap-2">
          <UiBadge :tone="sevTone[r.severity ?? 'mid']">{{ copy.analysis.severity[r.severity ?? 'mid'] }}</UiBadge>
          <span>
            {{ r.text }}
            <span v-if="r.source" class="text-sm text-text-3">{{ copy.analysis.source(r.source) }}</span>
          </span>
        </li>
      </ul>
    </section>

    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.fit }}</h3>
      <div class="mb-2 flex items-center gap-2">
        <ScoreBadge :score="analysis.fit.score" />
        <span class="font-medium">{{ copy.analysis.verdict[analysis.fit.verdict] }}</span>
      </div>
      <p class="mb-3 text-base">{{ analysis.fit.reasoning }}</p>
      <div class="grid gap-3 md:grid-cols-2">
        <div>
          <h4 class="mb-1 text-sm font-semibold text-text-2">{{ copy.analysis.strengths }}</h4>
          <ul class="list-disc pl-5">
            <li v-for="(s, i) in analysis.fit.strengths" :key="i">{{ s }}</li>
          </ul>
        </div>
        <div>
          <h4 class="mb-1 text-sm font-semibold text-text-2">{{ copy.analysis.gaps }}</h4>
          <ul class="list-disc pl-5">
            <li v-for="(g, i) in analysis.fit.gaps" :key="i">{{ g }}</li>
          </ul>
        </div>
      </div>
    </section>

    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.nextActions }}</h3>
      <ol class="list-decimal pl-5">
        <li v-for="(a, i) in analysis.next_actions" :key="i">{{ a }}</li>
      </ol>
    </section>

    <section v-if="analysis.warnings?.length">
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.warnings }}</h3>
      <ul class="list-disc pl-5 text-text-2">
        <li v-for="(w, i) in analysis.warnings" :key="i">{{ w }}</li>
      </ul>
    </section>
  </div>
</template>

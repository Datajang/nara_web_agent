<script setup lang="ts">
// 분석 결과 (SPEC §7.5-5). 순서 고정: 개요·요구사항·평가·일정·예산·리스크·적합도·다음 할 일.
import type { AnalysisResult } from '@/api/types'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'
import EvaluationBars from './EvaluationBars.vue'
import RequirementList from './RequirementList.vue'
import ScheduleTimeline from './ScheduleTimeline.vue'
import ScoreBadge from './ScoreBadge.vue'

defineProps<{ analysis: AnalysisResult }>()
const sevTone = { high: 'danger', mid: 'warning', low: 'neutral' } as const
</script>

<template>
  <div class="flex flex-col gap-6 [&>section+section]:border-t [&>section+section]:border-border [&>section+section]:pt-6">
    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.overview }}</h3>
      <p class="whitespace-pre-line text-base text-text">{{ analysis.overview }}</p>
    </section>

    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.requirements }}</h3>
      <p v-if="!analysis.requirements.length" class="text-text-3">{{ copy.analysis.none }}</p>
      <RequirementList v-else :items="analysis.requirements" detailed />
    </section>

    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.evaluation }}</h3>
      <p v-if="!analysis.evaluation.method && !analysis.evaluation.items?.length" class="text-text-3">
        {{ copy.analysis.none }}
      </p>
      <EvaluationBars v-else :evaluation="analysis.evaluation" />
    </section>

    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.schedule }}</h3>
      <p v-if="!analysis.schedule.length" class="text-text-3">{{ copy.analysis.none }}</p>
      <ScheduleTimeline v-else :items="analysis.schedule" />
    </section>

    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.budget }}</h3>
      <dl class="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 rounded-card bg-surface-2 px-4 py-3 text-base">
        <template
          v-for="[label, value] in [
            [copy.analysis.budgetText, analysis.budget_contract.budget_text],
            [copy.analysis.contractMethod, analysis.budget_contract.contract_method],
            [copy.analysis.payment, analysis.budget_contract.payment_terms],
            [copy.analysis.period, analysis.budget_contract.period],
          ]"
          :key="label"
        >
          <dt class="text-text-3">{{ label }}</dt>
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

<script setup lang="ts">
// 분석 결과 (SPEC §7.5-5, v10). 순서 고정: 사업 이해·적합도·(프로필 보완 안내)·필요한 것·리스크·다음 할 일.
// 일정·예산·평가·요구사항은 위 요약 카드에 있으므로 다시 보여 주지 않는다. 예전 분석은 Legacy 화면으로.
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { isLegacy, type AnalysisResult, type AnyAnalysis } from '@/api/types'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'
import AnalysisResultLegacy from './AnalysisResultLegacy.vue'
import ScoreBadge from './ScoreBadge.vue'

// fromTeam: 팀원이 팀 프로필로 만든 분석 — 프로필 보완 안내는 두되 '내 프로필 고치기' 링크는 뺀다
const props = defineProps<{ analysis: AnyAnalysis; fromTeam?: boolean }>()
const legacy = computed(() => (isLegacy(props.analysis) ? props.analysis : null))
const a = computed(() => (isLegacy(props.analysis) ? null : (props.analysis as AnalysisResult)))
const showProfileNotice = computed(
  () => !!a.value && (a.value.profile_brief || a.value.profile_missing.length > 0),
)
const sevTone = { high: 'danger', mid: 'warning', low: 'neutral' } as const
</script>

<template>
  <AnalysisResultLegacy v-if="legacy" :analysis="legacy" />
  <div
    v-else-if="a"
    class="flex flex-col gap-6 [&>section+section]:border-t [&>section+section]:border-border [&>section+section]:pt-6"
  >
    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.understanding }}</h3>
      <p class="whitespace-pre-line text-base text-text">{{ a.understanding.purpose }}</p>
      <div
        v-if="a.understanding.scope.length || a.understanding.conditions.length"
        class="mt-3 grid gap-3 md:grid-cols-2"
      >
        <div v-if="a.understanding.scope.length">
          <h4 class="mb-1 text-sm font-semibold text-text-2">{{ copy.analysis.scope }}</h4>
          <ul class="list-disc pl-5">
            <li v-for="(s, i) in a.understanding.scope" :key="i">{{ s }}</li>
          </ul>
        </div>
        <div v-if="a.understanding.conditions.length">
          <h4 class="mb-1 text-sm font-semibold text-text-2">{{ copy.analysis.conditions }}</h4>
          <ul class="list-disc pl-5">
            <li v-for="(c, i) in a.understanding.conditions" :key="i">{{ c }}</li>
          </ul>
        </div>
      </div>
    </section>

    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.fit }}</h3>
      <div class="mb-2 flex items-center gap-2">
        <ScoreBadge :score="a.fit.score" />
        <span class="font-medium">{{ copy.analysis.verdict[a.fit.verdict] }}</span>
      </div>
      <p class="text-base">{{ a.fit.reasoning }}</p>
    </section>

    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.teamNeeds }}</h3>
      <div
        v-if="showProfileNotice"
        data-test="profile-notice"
        role="note"
        class="mb-3 rounded-card bg-primary-soft px-4 py-3 text-base text-primary-hover"
      >
        <p class="font-medium">{{ copy.analysis.profileNotice }}</p>
        <template v-if="a.profile_missing.length">
          <p class="mt-2 text-sm">{{ copy.analysis.profileMissing }}</p>
          <ul class="list-disc pl-5 text-sm">
            <li v-for="(m, i) in a.profile_missing" :key="i">{{ m }}</li>
          </ul>
        </template>
        <RouterLink
          v-if="!fromTeam"
          to="/settings/profiles" class="mt-2 inline-block text-sm font-medium underline">
          {{ copy.analysis.editProfile }}
        </RouterLink>
      </div>
      <div class="grid gap-3 md:grid-cols-2">
        <div>
          <h4 class="mb-1 text-sm font-semibold text-text-2">{{ copy.analysis.have }}</h4>
          <p v-if="!a.team_needs.have.length" class="text-text-3">{{ copy.analysis.none }}</p>
          <ul v-else class="list-disc pl-5">
            <li v-for="(s, i) in a.team_needs.have" :key="i">{{ s }}</li>
          </ul>
        </div>
        <div>
          <h4 class="mb-1 text-sm font-semibold text-text-2">{{ copy.analysis.need }}</h4>
          <p v-if="!a.team_needs.need.length" class="text-text-3">{{ copy.analysis.none }}</p>
          <ul v-else class="list-disc pl-5">
            <li v-for="(g, i) in a.team_needs.need" :key="i">{{ g }}</li>
          </ul>
        </div>
      </div>
    </section>

    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.risks }}</h3>
      <p v-if="!a.risks.length" class="text-text-3">{{ copy.analysis.none }}</p>
      <ul v-else class="flex flex-col gap-2">
        <li v-for="(r, i) in a.risks" :key="i" class="flex items-start gap-2">
          <UiBadge :tone="sevTone[r.severity ?? 'mid']">{{ copy.analysis.severity[r.severity ?? 'mid'] }}</UiBadge>
          <span>
            {{ r.text }}
            <span v-if="r.source" class="text-sm text-text-3">{{ copy.analysis.source(r.source) }}</span>
          </span>
        </li>
      </ul>
    </section>

    <section>
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.nextActions }}</h3>
      <ol class="list-decimal pl-5">
        <li v-for="(x, i) in a.next_actions" :key="i">{{ x }}</li>
      </ol>
    </section>

    <section v-if="a.warnings?.length">
      <h3 class="mb-2 text-lg font-semibold">{{ copy.analysis.warnings }}</h3>
      <ul class="list-disc pl-5 text-text-2">
        <li v-for="(w, i) in a.warnings" :key="i">{{ w }}</li>
      </ul>
    </section>
  </div>
</template>

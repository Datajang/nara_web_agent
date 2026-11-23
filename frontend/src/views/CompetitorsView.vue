<script setup lang="ts">
// 경쟁사 레이더 (§15.7 /competitors): 우리 회사 요약, 필터(분야·수요기관), 겹침도 순 후보 표, 관심 경쟁사 목록.
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { awardsApi, formatBizno } from '@/api/awards'
import { ApiError } from '@/api/client'
import { competitorsApi } from '@/api/competitors'
import AwardsBasis from '@/components/awards/AwardsBasis.vue'
import AwardsFootnote from '@/components/awards/AwardsFootnote.vue'
import WatchButton from '@/components/awards/WatchButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { copy } from '@/copy'
import { useAuthStore } from '@/stores/auth'
import { formatDate, formatPct } from '@/utils/format'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const field = computed({
  get: () => (typeof route.query.field === 'string' ? route.query.field : ''),
  set: (v: string) => void router.replace({ query: { ...route.query, field: v || undefined } }),
})
const org = computed({
  get: () => (typeof route.query.org === 'string' ? route.query.org : ''),
  set: (v: string) => void router.replace({ query: { ...route.query, org: v || undefined } }),
})

const summary = useQuery({ queryKey: ['awards-summary', 'us'], queryFn: () => awardsApi.summary() })
const cands = useQuery({
  queryKey: computed(() => ['competitors', 'candidates', field.value, org.value]),
  queryFn: () => competitorsApi.candidates({ field: field.value, org: org.value }),
  enabled: computed(() => !!summary.data.value),
})
const watched = useQuery({ queryKey: ['competitors', 'watch'], queryFn: competitorsApi.watched })
/** 내 목록에 있는 곳: 팀 목록의 별 버튼이 내 관심 여부를 보여 준다 */
const watchedSet = computed(() => new Set((watched.data.value?.items ?? []).map((w) => w.bizno)))
const notConfigured = computed(
  () => summary.error.value instanceof ApiError && summary.error.value.code === 'not_configured',
)

const fieldOptions = computed(() => [
  { value: '', label: copy.awards.allFields },
  ...(summary.data.value?.fields ?? []).map((f) => ({ value: f, label: f })),
])
const orgOptions = computed(() => [
  { value: '', label: copy.awards.allOrgs },
  ...(summary.data.value?.by_org ?? [])
    .filter((o) => o.dminstt_cd)
    .map((o) => ({ value: o.dminstt_cd as string, label: o.dminstt_name ?? (o.dminstt_cd as string) })),
])
</script>

<template>
  <div class="flex flex-col gap-4">
    <UiSkeleton v-if="summary.isPending.value" :lines="3" />
    <EmptyState v-else-if="notConfigured" :title="copy.awards.notConfiguredTitle" :description="copy.awards.notConfiguredBody">
      <template v-if="auth.isAdmin" #action>
        <RouterLink to="/admin/company" class="inline-flex h-10 items-center rounded-control bg-primary px-4 text-white hover:bg-primary-hover">
          {{ copy.awards.goCompanySettings }}
        </RouterLink>
      </template>
    </EmptyState>
    <div v-else-if="summary.isError.value" class="flex items-center gap-3 text-danger-fg" role="alert">
      {{ copy.awards.loadFailed }}
      <UiButton size="sm" variant="secondary" @click="summary.refetch()">{{ copy.common.retry }}</UiButton>
    </div>
    <template v-else-if="summary.data.value">
      <header class="flex flex-col gap-2">
        <p class="text-lg font-semibold">{{ copy.competitors.ourSummary(summary.data.value.name, summary.data.value.count) }}</p>
        <AwardsBasis :period="summary.data.value.period" />
      </header>

      <div class="grid items-start gap-4 2xl:grid-cols-[minmax(0,1fr)_22rem]">
        <section class="min-w-0 rounded-card border border-border bg-surface p-4" :aria-label="copy.competitors.radar">
          <div class="mb-3 flex flex-wrap items-end gap-3">
            <div class="w-full sm:mr-auto sm:w-auto">
              <h3 class="text-lg font-semibold">{{ copy.competitors.radar }}</h3>
              <p class="text-sm text-text-2">{{ copy.competitors.radarIntro }}</p>
            </div>
            <div class="w-full sm:w-44"><UiSelect v-model="field" :label="copy.awards.filterField" :options="fieldOptions" /></div>
            <div class="w-full sm:w-56"><UiSelect v-model="org" :label="copy.awards.filterOrg" :options="orgOptions" /></div>
          </div>
          <p class="mb-2 text-xs text-text-3">{{ copy.competitors.overlapHelp }}</p>
          <UiSkeleton v-if="cands.isPending.value" :lines="2" />
          <p v-else-if="cands.isError.value" class="text-danger-fg" role="alert">{{ copy.awards.loadFailed }}</p>
          <p v-else-if="!cands.data.value?.items.length" class="py-6 text-center text-text-3">{{ copy.competitors.noCandidates }}</p>
          <div v-else class="overflow-x-auto">
            <table class="w-full min-w-[720px] text-sm" data-candidates>
              <thead class="bg-surface-2 text-left text-xs font-semibold text-text-3">
                <tr>
                  <th scope="col" class="w-14 whitespace-nowrap px-3 py-2 text-right">{{ copy.competitors.colRank }}</th>
                  <th scope="col" class="px-3 py-2">{{ copy.competitors.colCompany }}</th>
                  <th scope="col" class="w-56 px-3 py-2">{{ copy.competitors.colOverlap }}</th>
                  <th scope="col" class="px-3 py-2 text-right">{{ copy.competitors.colAwards }}</th>
                  <th scope="col" class="px-3 py-2">{{ copy.competitors.colLast }}</th>
                  <th scope="col" class="px-3 py-2">{{ copy.competitors.colWatch }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(c, i) in cands.data.value.items" :key="c.bizno" class="border-t border-border align-middle">
                  <td class="px-3 py-2 text-right tabular text-text-2">{{ i + 1 }}</td>
                  <td class="px-3 py-2">
                    <RouterLink :to="`/competitors/${c.bizno}`" class="font-medium text-primary hover:underline">{{ c.name }}</RouterLink>
                    <span class="block text-xs text-text-3 tabular">{{ formatBizno(c.bizno) }}</span>
                  </td>
                  <td class="px-3 py-2">
                    <span class="flex items-center gap-2">
                      <span class="h-2 flex-1 rounded-sm bg-surface-2" aria-hidden="true">
                        <span class="block h-2 rounded-r-[4px] bg-primary" :style="{ width: `${c.overlap}%` }" />
                      </span>
                      <span class="w-10 text-right font-semibold tabular">{{ formatPct(c.overlap) }}</span>
                    </span>
                    <span class="block text-xs text-text-3 tabular">
                      {{ copy.competitors.overlapDetail(formatPct(c.org_overlap * 100), formatPct(c.field_overlap * 100)) }}
                    </span>
                  </td>
                  <td class="px-3 py-2 text-right tabular">{{ copy.awards.countUnit(c.award_count) }}</td>
                  <td class="px-3 py-2 tabular text-text-2">{{ c.last_award_at ? formatDate(c.last_award_at) : '' }}</td>
                  <td class="px-3 py-2"><WatchButton :bizno="c.bizno" :watched="c.watched" /></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="rounded-card border border-border bg-surface p-4" :aria-label="copy.competitors.myWatchList">
          <h3 class="mb-3 text-lg font-semibold">{{ copy.competitors.myWatchList }}</h3>
          <p v-if="!watched.data.value?.items.length" class="text-text-3">{{ copy.competitors.noWatched }}</p>
          <ul v-else class="flex flex-col divide-y divide-border" data-watch-list>
            <li v-for="w in watched.data.value.items" :key="w.bizno" class="flex flex-wrap items-center gap-3 py-2 text-sm">
              <RouterLink :to="`/competitors/${w.bizno}`" class="min-w-0 flex-1 truncate font-medium text-primary hover:underline">{{ w.name }}</RouterLink>
              <span class="tabular text-text-2">{{ copy.awards.countUnit(w.award_count) }}</span>
              <span v-if="w.last_award_at" class="tabular text-text-3">{{ copy.companies.lastAward(formatDate(w.last_award_at)) }}</span>
              <WatchButton :bizno="w.bizno" :watched="true" />
            </li>
          </ul>
        </section>

        <!-- 팀 목록: 팀원(나 포함)이 담은 곳을 담은 사람과 함께 모아 보여 준다 (2026-11-23) -->
        <section
          v-if="watched.data.value?.team"
          class="rounded-card border border-border bg-surface p-4"
          :aria-label="copy.competitors.teamWatchList(watched.data.value.team.name)"
        >
          <h3 class="mb-3 text-lg font-semibold">{{ copy.competitors.teamWatchList(watched.data.value.team.name) }}</h3>
          <p v-if="!watched.data.value.team.items.length" class="text-text-3">{{ copy.competitors.noTeamWatched }}</p>
          <ul v-else class="flex flex-col divide-y divide-border" data-team-watch-list>
            <li v-for="w in watched.data.value.team.items" :key="w.bizno" class="flex flex-wrap items-center gap-3 py-2 text-sm">
              <RouterLink :to="`/competitors/${w.bizno}`" class="min-w-0 flex-1 truncate font-medium text-primary hover:underline">{{ w.name }}</RouterLink>
              <span class="tabular text-text-2">{{ copy.awards.countUnit(w.award_count) }}</span>
              <span v-if="w.last_award_at" class="tabular text-text-3">{{ copy.companies.lastAward(formatDate(w.last_award_at)) }}</span>
              <span class="text-text-3">{{ copy.competitors.addedBy(w.added_by ?? []) }}</span>
              <WatchButton :bizno="w.bizno" :watched="watchedSet.has(w.bizno)" />
            </li>
          </ul>
        </section>
      </div>
      <AwardsFootnote />
    </template>
  </div>
</template>

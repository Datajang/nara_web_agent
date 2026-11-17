<script setup lang="ts">
// 우리 수주 현황 (§15.7 /my-awards): 요약 카드 4개, 연도별·수요기관별, 분야 태그, 낙찰 목록.
// 수집 전 기간은 0건이 아니라 '수집 중'. 회사가 설정되지 않았으면 빈 상태와 회사 설정 링크.
// '투찰 결과' 탭(P12): 낙찰·탈락 목록. 탭은 URL ?tab=bids와 맞춘다.
import { useQuery } from '@tanstack/vue-query'
import { computed, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { awardsApi } from '@/api/awards'
import { ApiError } from '@/api/client'
import AwardsBasis from '@/components/awards/AwardsBasis.vue'
import AwardsFootnote from '@/components/awards/AwardsFootnote.vue'
import AwardSummaryView from '@/components/awards/AwardSummaryView.vue'
import AwardTable from '@/components/awards/AwardTable.vue'
import MyBidsPanel from '@/components/awards/MyBidsPanel.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import UiTabs from '@/components/ui/UiTabs.vue'
import { copy } from '@/copy'
import { useAuthStore } from '@/stores/auth'
import { formatBizno } from '@/api/awards'

const auth = useAuthStore()
const summary = useQuery({ queryKey: ['awards-summary', 'us'], queryFn: () => awardsApi.summary() })
const notConfigured = computed(
  () => summary.error.value instanceof ApiError && summary.error.value.code === 'not_configured',
)
const field = ref('')
const org = ref('')

const route = useRoute()
const router = useRouter()
type Tab = 'awards' | 'bids'
const TABS: Array<{ value: Tab; label: string }> = [
  { value: 'awards', label: copy.myBids.tabAwards },
  { value: 'bids', label: copy.myBids.tabBids },
]
const tab = computed<Tab>({
  get: () => TABS.find((t) => t.value === route.query.tab)?.value ?? 'awards',
  set: (v) => void router.replace({ query: v === 'awards' ? {} : { tab: v } }),
})
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
        <p class="text-lg font-semibold">
          {{ summary.data.value.name }}
          <span class="ml-2 text-sm font-normal text-text-2 tabular">{{ copy.companies.biznoLabel(formatBizno(summary.data.value.bizno)) }}</span>
        </p>
        <AwardsBasis :period="summary.data.value.period" />
      </header>
      <UiTabs v-model="tab" :items="TABS" :label="copy.myBids.tabsLabel" />
      <MyBidsPanel v-if="tab === 'bids'" />
      <template v-else>
        <AwardSummaryView v-model:field="field" v-model:org="org" :summary="summary.data.value" />
        <AwardTable v-model:field="field" v-model:org="org" :summary="summary.data.value" />
      </template>
      <AwardsFootnote />
    </template>
  </div>
</template>

<script setup lang="ts">
// 업체 검색 (§15.7 /companies): 업체명 일부·사업자번호로 찾고, 고른 업체의 요약·낙찰 목록.
// 조건은 URL(?q=, ?bizno=)에 남겨 새로고침·링크 공유 때 복원한다. 비교·관심 경쟁사는 P10.
import { useQuery } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { awardsApi, formatBizno, normalizeBizno } from '@/api/awards'
import { ApiError } from '@/api/client'
import AwardsBasis from '@/components/awards/AwardsBasis.vue'
import AwardsFootnote from '@/components/awards/AwardsFootnote.vue'
import AwardSummaryView from '@/components/awards/AwardSummaryView.vue'
import AwardTable from '@/components/awards/AwardTable.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { copy } from '@/copy'
import { formatDate } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const q = computed(() => (typeof route.query.q === 'string' ? route.query.q : ''))
const bizno = computed(() => (typeof route.query.bizno === 'string' ? normalizeBizno(route.query.bizno) : null))
const input = ref(q.value)
const inputError = ref('')
watch(q, (v) => (input.value = v))

/** 글자는 기호·공백을 빼고 두 글자 이상, 숫자는 10자리. 법인 표기만 남는 경우는 서버가 422로 막는다. */
function valid(v: string): boolean {
  const t = v.trim()
  if (/^[\d\s-]+$/.test(t)) return normalizeBizno(t) !== null
  return t.replace(/[^\p{L}\p{N}]/gu, '').length >= 2
}

function submit() {
  if (!valid(input.value)) {
    inputError.value = copy.companies.tooShort
    return
  }
  inputError.value = ''
  void router.replace({ query: { q: input.value.trim() } })
}

const results = useQuery({
  queryKey: computed(() => ['company-search', q.value]),
  queryFn: () => awardsApi.search(q.value),
  enabled: computed(() => valid(q.value)),
})
const detail = useQuery({
  queryKey: computed(() => ['company', bizno.value]),
  queryFn: () => awardsApi.companySummary(bizno.value as string),
  enabled: computed(() => bizno.value !== null),
})
const field = ref('')
const org = ref('')
watch(bizno, () => {
  field.value = ''
  org.value = ''
})

function pick(b: string) {
  void router.replace({ query: { ...route.query, bizno: b } })
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <form class="flex flex-wrap items-start gap-3 rounded-card border border-border bg-surface p-4" role="search" @submit.prevent="submit">
      <div class="min-w-64 flex-1">
        <UiInput v-model="input" :label="copy.companies.searchLabel" :hint="copy.companies.searchHint" :error="inputError" :max-length="100" />
      </div>
      <UiButton type="submit" class="mt-7">{{ copy.companies.submit }}</UiButton>
    </form>

    <div class="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <section v-if="q" class="self-start rounded-card border border-border bg-surface p-2" :aria-label="copy.companies.results">
        <h3 class="px-2 py-1 text-base font-semibold">{{ copy.companies.results }}</h3>
        <UiSkeleton v-if="results.isPending.value && results.fetchStatus.value !== 'idle'" :lines="2" />
        <p v-else-if="results.isError.value" class="p-2 text-danger-fg" role="alert">
          {{ results.error.value instanceof ApiError && results.error.value.status === 422 ? copy.companies.tooShort : copy.awards.loadFailed }}
        </p>
        <p v-else-if="!results.data.value?.items.length" class="p-2 text-text-3">{{ copy.companies.noResults }}</p>
        <ul v-else class="flex flex-col">
          <li v-for="h in results.data.value.items" :key="h.bizno">
            <button
              type="button"
              class="flex w-full flex-col gap-0.5 rounded-control px-2 py-2 text-left hover:bg-surface-2"
              :class="bizno === h.bizno ? 'bg-primary-soft' : ''"
              :aria-current="bizno === h.bizno ? 'true' : undefined"
              data-company-hit
              @click="pick(h.bizno)"
            >
              <span class="flex items-center gap-2 font-medium">
                {{ h.name }}<UiBadge v-if="h.is_us" tone="primary">{{ copy.companies.us }}</UiBadge>
              </span>
              <span class="text-xs text-text-2 tabular">
                {{ formatBizno(h.bizno) }} · {{ copy.companies.awardCount(h.award_count) }}
                <template v-if="h.last_award_at"> · <span class="whitespace-nowrap">{{ copy.companies.lastAward(formatDate(h.last_award_at)) }}</span></template>
              </span>
            </button>
          </li>
        </ul>
      </section>

      <div class="flex min-w-0 flex-col gap-4" :class="q ? '' : 'lg:col-span-2'">
        <p v-if="!bizno" class="rounded-card border border-dashed border-border p-6 text-center text-text-3">{{ copy.companies.pick }}</p>
        <UiSkeleton v-else-if="detail.isPending.value" :lines="3" />
        <p v-else-if="detail.isError.value" class="text-danger-fg" role="alert">{{ copy.awards.loadFailed }}</p>
        <template v-else-if="detail.data.value">
          <header class="flex flex-col gap-2">
            <p class="text-lg font-semibold">
              {{ detail.data.value.name }}
              <UiBadge v-if="detail.data.value.is_us" tone="primary">{{ copy.companies.us }}</UiBadge>
              <span class="ml-2 text-sm font-normal text-text-2 tabular">{{ copy.companies.biznoLabel(formatBizno(detail.data.value.bizno)) }}</span>
            </p>
            <AwardsBasis :period="detail.data.value.period" />
          </header>
          <AwardSummaryView v-model:field="field" v-model:org="org" :summary="detail.data.value" />
          <AwardTable v-model:field="field" v-model:org="org" :summary="detail.data.value" :bizno="detail.data.value.bizno" />
        </template>
      </div>
    </div>
    <AwardsFootnote />
  </div>
</template>

<script setup lang="ts">
// 낙찰 목록 (§15.7): 분야·수요기관 필터, 커서 '더 보기'.
// filterable이면 연도·기간·사업명 필터도 둔다(우리 수주 현황, 2026-11-24).
// 추정가격 대비는 값이 있을 때만, 없으면 낙찰률(G2B), 그것도 없으면 '정보 없음' (§15.1 원칙 4).
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { awardsApi, NO_NARROW, type Award, type AwardNarrow, type AwardSummary } from '@/api/awards'
import AwardsFilter from '@/components/awards/AwardsFilter.vue'
import MoneyText from '@/components/bid/MoneyText.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import { copy } from '@/copy'
import { formatDate, formatPct } from '@/utils/format'

const props = defineProps<{ summary: AwardSummary; bizno?: string; showWinner?: boolean; filterable?: boolean }>()
const field = defineModel<string>('field', { default: '' })
const org = defineModel<string>('org', { default: '' })
const narrow = ref<AwardNarrow>({ ...NO_NARROW })
const years = computed(() => props.summary.by_year.map((y) => y.year))
const narrowed = computed(() => Boolean(narrow.value.from || narrow.value.to || narrow.value.q))

const items = ref<Award[]>([])
const total = ref(0)
const cursor = ref<string | null>(null)
const loading = ref(false)
const failed = ref(false)

const fieldOptions = computed(() => [
  { value: '', label: copy.awards.allFields },
  ...props.summary.fields.map((f) => ({ value: f, label: f })),
])
const orgOptions = computed(() => {
  const opts = props.summary.by_org
    .filter((o) => o.dminstt_cd)
    .map((o) => ({ value: o.dminstt_cd as string, label: o.dminstt_name ?? (o.dminstt_cd as string) }))
  if (org.value && !opts.some((o) => o.value === org.value)) opts.push({ value: org.value, label: org.value })
  return [{ value: '', label: copy.awards.allOrgs }, ...opts]
})

async function load(reset: boolean) {
  loading.value = true
  failed.value = false
  try {
    const page = await awardsApi.list({
      bizno: props.bizno,
      field: field.value,
      org: org.value,
      ...narrow.value,
      cursor: reset ? null : cursor.value,
    })
    items.value = reset ? page.items : [...items.value, ...page.items]
    total.value = page.total
    cursor.value = page.next_cursor ?? null
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

watch([field, org, narrow, () => props.bizno], () => load(true), { immediate: true })

function rateText(a: Award): string {
  if (a.award_ratio != null) return copy.awards.ratio(formatPct(a.award_ratio * 100))
  if (a.g2b_award_rate != null) return copy.awards.g2bRate(formatPct(a.g2b_award_rate))
  return copy.awards.noRate
}

const dateOf = (a: Award) => a.awarded_on ?? formatDate(a.registered_at)
</script>

<template>
  <section class="rounded-card border border-border bg-surface p-4" :aria-label="copy.awards.list">
    <div class="mb-3 flex flex-wrap items-end gap-3">
      <h3 class="w-full text-lg font-semibold sm:mr-auto sm:w-auto">
        {{ copy.awards.list }}
        <span class="ml-2 text-sm font-normal text-text-2" aria-live="polite">{{ copy.awards.listTotal(total) }}</span>
      </h3>
      <div class="w-full sm:w-44"><UiSelect v-model="field" :label="copy.awards.filterField" :options="fieldOptions" /></div>
      <div class="w-full sm:w-56"><UiSelect v-model="org" :label="copy.awards.filterOrg" :options="orgOptions" /></div>
    </div>
    <AwardsFilter v-if="filterable" v-model="narrow" :years="years" class="mb-3" />
    <p class="mb-2 text-xs text-text-3">{{ copy.awards.rateHelp }}</p>

    <p v-if="failed" class="flex items-center gap-3 text-danger-fg" role="alert">
      {{ copy.awards.loadFailed }}
      <UiButton size="sm" variant="secondary" @click="load(items.length === 0)">{{ copy.common.retry }}</UiButton>
    </p>
    <p v-else-if="!loading && !items.length" class="py-6 text-center text-text-3">
      {{ narrowed ? copy.awards.emptyFiltered : copy.awards.emptyList }}
    </p>
    <div v-else class="overflow-x-auto">
      <table class="w-full min-w-[760px] text-sm" data-award-table>
        <thead class="bg-surface-2 text-left text-text-2">
          <tr>
            <th scope="col" class="px-3 py-2">{{ copy.awards.colDate }}</th>
            <th scope="col" class="px-3 py-2">{{ copy.awards.colTitle }}</th>
            <th scope="col" class="px-3 py-2">{{ copy.awards.colOrg }}</th>
            <th v-if="showWinner" scope="col" class="px-3 py-2">{{ copy.awards.colWinner }}</th>
            <th scope="col" class="px-3 py-2 text-right">{{ copy.awards.colAmount }}</th>
            <th scope="col" class="px-3 py-2">{{ copy.awards.colRate }}</th>
            <th scope="col" class="px-3 py-2 text-right">{{ copy.awards.colParticipants }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in items" :key="`${a.bid_ntce_no}-${a.bid_ntce_ord}-${a.registered_at}`" class="border-t border-border align-top">
            <td class="whitespace-nowrap px-3 py-2 tabular">{{ dateOf(a) }}</td>
            <td class="px-3 py-2">
              <RouterLink v-if="a.bid_id" :to="`/bids/${a.bid_id}`" class="text-primary hover:underline">{{ a.title }}</RouterLink>
              <span v-else>{{ a.title }}</span>
              <span class="mt-1 flex flex-wrap gap-1">
                <UiBadge v-for="f in a.fields" :key="f">{{ f }}</UiBadge>
                <UiBadge v-if="a.is_joint" tone="primary">{{ copy.awards.joint }}</UiBadge>
              </span>
            </td>
            <td class="px-3 py-2 text-text-2">{{ a.dminstt_name }}</td>
            <td v-if="showWinner" class="px-3 py-2">{{ a.winner_name }}</td>
            <td class="whitespace-nowrap px-3 py-2 text-right"><MoneyText :value="a.award_amount" /></td>
            <td class="whitespace-nowrap px-3 py-2 text-text-2 tabular" data-rate>{{ rateText(a) }}</td>
            <td class="whitespace-nowrap px-3 py-2 text-right tabular">
              {{ a.participant_count != null ? copy.awards.participants(a.participant_count) : '' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="cursor && !failed" class="mt-3 flex justify-center">
      <UiButton variant="secondary" :loading="loading" @click="load(false)">{{ copy.awards.loadMore }}</UiButton>
    </div>
  </section>
</template>

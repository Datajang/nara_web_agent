<script setup lang="ts">
// 회사 설정 · 수집 현황 (§15.7 /company, 관리자 전용).
// 사업자번호 → '이름 찾기'(수집된 낙찰에서) → 없으면 직접 입력. 분야 키워드, 수집 기간, 연도별 진행률, 오늘 호출량.
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'
import {
  awardsApi,
  formatBizno,
  keywordsToText,
  normalizeBizno,
  parseKeywords,
  type CompanyStatus,
  type Lookup,
} from '@/api/awards'
import { ApiError } from '@/api/client'
import SubNav from '@/components/layout/SubNav.vue'
import { ADMIN_NAV } from '@/components/layout/subnavs'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import UiTextarea from '@/components/ui/UiTextarea.vue'
import { copy } from '@/copy'
import { useUiStore } from '@/stores/ui'
import { generalMessage } from '@/utils/authErrors'
import { formatDate, formatPct } from '@/utils/format'

const ui = useUiStore()
const queryClient = useQueryClient()
const status = useQuery({ queryKey: ['company'], queryFn: awardsApi.company })

const bizno = ref('')
const name = ref('')
const fieldsText = ref('')
const years = ref(5)
const lookup = ref<Lookup | null>(null)
const errors = ref<{ bizno?: string; name?: string; fields?: string }>({})
const looking = ref(false)
const saving = ref(false)

function fill(c: CompanyStatus) {
  bizno.value = c.our_bizno ? formatBizno(c.our_bizno) : ''
  name.value = c.our_name ?? ''
  fieldsText.value = keywordsToText(c.field_keywords)
  years.value = c.backfill_years
}
watch(
  () => status.data.value,
  (c) => c && fill(c),
  { immediate: true },
)

const yearOptions = Array.from({ length: 10 }, (_, i) => ({ value: i + 1, label: copy.company.yearsOption(i + 1) }))

async function findName() {
  const b = normalizeBizno(bizno.value)
  errors.value = { ...errors.value, bizno: b ? undefined : copy.company.biznoInvalid }
  if (!b) return
  looking.value = true
  try {
    lookup.value = await awardsApi.lookup(b)
    if (lookup.value.found && lookup.value.name) name.value = lookup.value.name
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  } finally {
    looking.value = false
  }
}

async function save() {
  const b = bizno.value.trim() ? normalizeBizno(bizno.value) : null
  const parsed = parseKeywords(fieldsText.value)
  errors.value = {
    bizno: bizno.value.trim() && !b ? copy.company.biznoInvalid : undefined,
    fields: 'errorLine' in parsed ? copy.company.fieldsInvalid(parsed.errorLine) : undefined,
  }
  if (errors.value.bizno || errors.value.fields || 'errorLine' in parsed) return
  saving.value = true
  try {
    const res = await awardsApi.saveCompany({
      our_bizno: b,
      our_name: name.value.trim() || null,
      field_keywords: parsed.value,
      backfill_years: years.value,
    })
    queryClient.setQueryData(['company'], res)
    void queryClient.invalidateQueries({ queryKey: ['awards-summary'] })
    ui.toast(res.reclassify_started ? copy.company.reclassifying : copy.company.saved, 'success')
  } catch (e) {
    if (e instanceof ApiError && e.reason('our_name')) errors.value = { ...errors.value, name: copy.company.nameRequired }
    else ui.toast(generalMessage(e), 'danger')
  } finally {
    saving.value = false
  }
}

const progress = computed(() => status.data.value?.years ?? [])
</script>

<template>
  <div class="flex flex-col gap-4">
    <SubNav :label="copy.nav.adminLabel" :items="ADMIN_NAV" />
    <UiSkeleton v-if="status.isPending.value" :lines="2" />
    <template v-else-if="status.data.value">
      <form class="flex flex-col gap-4 rounded-card border border-border bg-surface p-4" :aria-label="copy.company.title" @submit.prevent="save">
        <p class="text-text-2">{{ copy.company.intro }}</p>
        <div class="flex flex-wrap items-start gap-3">
          <div class="w-60">
            <UiInput v-model="bizno" :label="copy.company.bizno" :hint="copy.company.biznoHint" :error="errors.bizno" :max-length="20" />
          </div>
          <UiButton variant="secondary" class="mt-7" :loading="looking" @click="findName">{{ copy.company.lookup }}</UiButton>
          <div class="min-w-60 flex-1">
            <UiInput v-model="name" :label="copy.company.name" :error="errors.name" :max-length="100" />
          </div>
        </div>
        <p v-if="lookup" class="text-sm" :class="lookup.found ? 'text-success-fg' : 'text-warning-fg'" role="status" data-lookup>
          {{ lookup.found && lookup.name ? copy.company.found(lookup.name, lookup.award_count) : copy.company.notFound }}
        </p>
        <UiTextarea
          v-model="fieldsText"
          :label="copy.company.fields"
          :hint="copy.company.fieldsHint"
          :error="errors.fields"
          :placeholder="copy.company.fieldsPlaceholder"
          :rows="5"
        />
        <div class="w-40"><UiSelect v-model="years" :label="copy.company.years" :options="yearOptions" /></div>
        <div><UiButton type="submit" :loading="saving">{{ copy.company.save }}</UiButton></div>
      </form>

      <section class="flex flex-col gap-3 rounded-card border border-border bg-surface p-4" :aria-label="copy.company.statusTitle">
        <h3 class="text-lg font-semibold">{{ copy.company.statusTitle }}</h3>
        <p class="text-base">
          <span class="font-medium">{{ copy.company.coverage }}</span>
          <span v-if="status.data.value.coverage.covered_from && status.data.value.coverage.covered_to" class="ml-2 tabular text-text-2">
            {{ formatDate(status.data.value.coverage.covered_from) }} ~ {{ formatDate(status.data.value.coverage.covered_to) }}
          </span>
          <span v-else class="ml-2 text-text-3">{{ copy.company.noCoverage }}</span>
          <UiBadge v-if="status.data.value.coverage.collecting" tone="warning" class="ml-2">{{ copy.awards.collecting }}</UiBadge>
        </p>
        <ul class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" data-year-progress>
          <li v-for="y in progress" :key="y.year" class="flex items-center gap-3 text-sm">
            <span class="w-14 shrink-0 whitespace-nowrap tabular text-text-2">{{ copy.awards.yearLabel(y.year) }}</span>
            <span
              class="h-2 flex-1 rounded-sm bg-surface-2"
              role="progressbar"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-valuenow="Math.round(y.ratio * 100)"
              :aria-label="copy.company.yearProgress(y.year)"
            >
              <span class="block h-2 rounded-r-[4px] bg-primary" :style="{ width: `${y.ratio * 100}%` }" />
            </span>
            <span class="w-12 shrink-0 text-right tabular">{{ y.ratio >= 1 ? copy.company.done : `${formatPct(y.ratio * 100)}%` }}</span>
          </li>
        </ul>
        <p class="text-base">
          <span class="font-medium">{{ copy.company.callsToday }}</span>
          <span class="ml-2 tabular text-text-2">{{ copy.company.calls(status.data.value.calls_today, status.data.value.calls_budget) }}</span>
        </p>
        <p class="text-base" data-openings-calls>
          <span class="font-medium">{{ copy.company.openingsCallsToday }}</span>
          <span class="ml-2 tabular text-text-2">{{
            copy.company.calls(status.data.value.openings_calls_today, status.data.value.openings_calls_budget)
          }}</span>
          <span class="block text-sm text-text-3">{{ copy.company.openingsCallsHelp }}</span>
        </p>
        <p v-if="status.data.value.unidentified_count" class="text-sm text-text-3">
          {{ copy.awards.unidentified(status.data.value.unidentified_count) }}
        </p>
      </section>
    </template>
  </div>
</template>

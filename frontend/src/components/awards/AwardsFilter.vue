<script setup lang="ts">
// 우리 수주 현황 목록 필터(2026-11-24): 연도 · 시작일~종료일 · 사업명. 낙찰 목록과 투찰 결과가 같이 쓴다.
// 연도를 고르면 그해 1/1~12/31로 날짜를 채우고, 날짜를 직접 고치면 '기간 직접 지정'이 된다.
// 날짜는 바로 적용하고 사업명은 Enter(검색)로 적용한다(글자마다 부르지 않게).
// 시작일이 종료일보다 늦으면 안내만 하고 적용하지 않는다.
import { computed, ref, watch } from 'vue'
import type { AwardNarrow } from '@/api/awards'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import { copy } from '@/copy'

const props = defineProps<{ years: number[] }>()
const model = defineModel<AwardNarrow>({ required: true })

const from = ref(model.value.from)
const to = ref(model.value.to)
const draftQ = ref(model.value.q)
watch(model, (v) => {
  from.value = v.from
  to.value = v.to
  draftQ.value = v.q
})

const yearsDesc = computed(() => [...new Set(props.years)].sort((a, b) => b - a))
const fullYear = (y: number) => ({ from: `${y}-01-01`, to: `${y}-12-31` })
const year = computed<string>({
  get: () => {
    if (!from.value && !to.value) return ''
    const y = yearsDesc.value.find((n) => from.value === fullYear(n).from && to.value === fullYear(n).to)
    return y !== undefined ? String(y) : 'custom'
  },
  set: (v) => {
    if (v === 'custom') return
    const range = v ? fullYear(Number(v)) : { from: '', to: '' }
    from.value = range.from
    to.value = range.to
  },
})
const yearOptions = computed(() => [
  { value: '', label: copy.awardFilter.allYears },
  ...yearsDesc.value.map((y) => ({ value: String(y), label: copy.awardFilter.year(y) })),
  ...(year.value === 'custom' ? [{ value: 'custom', label: copy.awardFilter.custom }] : []),
])

const badRange = computed(() => Boolean(from.value && to.value && from.value > to.value))
watch([from, to], () => {
  if (badRange.value) return
  if (from.value === model.value.from && to.value === model.value.to) return
  model.value = { ...model.value, from: from.value, to: to.value }
})

function submitSearch() {
  const q = draftQ.value.trim()
  if (q !== model.value.q) model.value = { ...model.value, q }
}

const active = computed(() => Boolean(model.value.from || model.value.to || model.value.q))
function reset() {
  model.value = { from: '', to: '', q: '' }
}
</script>

<template>
  <div class="flex flex-col gap-2" role="group" :aria-label="copy.awardFilter.label" data-awards-filter>
    <div class="flex flex-wrap items-end gap-3">
      <div class="w-full sm:w-36" data-filter-year>
        <UiSelect v-model="year" :label="copy.awardFilter.yearLabel" :options="yearOptions" />
      </div>
      <UiInput v-model="from" type="date" :label="copy.awardFilter.from" class="w-[calc(50%-0.375rem)] sm:w-40" data-filter-from />
      <UiInput v-model="to" type="date" :label="copy.awardFilter.to" class="w-[calc(50%-0.375rem)] sm:w-40" data-filter-to />
      <form class="flex min-w-0 flex-1 items-end gap-2 sm:min-w-64" role="search" data-filter-search @submit.prevent="submitSearch">
        <UiInput
          v-model="draftQ"
          type="search"
          name="award-q"
          :label="copy.awardFilter.search"
          :placeholder="copy.awardFilter.searchPlaceholder"
          :max-length="100"
          class="min-w-0 flex-1"
        />
        <UiButton type="submit" variant="secondary">{{ copy.awardFilter.submit }}</UiButton>
      </form>
      <UiButton v-if="active" variant="ghost" data-filter-reset @click="reset">{{ copy.awardFilter.reset }}</UiButton>
    </div>
    <p v-if="badRange" role="alert" class="text-sm text-danger-fg">{{ copy.awardFilter.badRange }}</p>
    <p v-else class="text-xs text-text-3">{{ copy.awardFilter.basis }}</p>
  </div>
</template>

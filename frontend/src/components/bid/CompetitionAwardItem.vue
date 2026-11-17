<script setup lang="ts">
// 경쟁 구도의 낙찰 한 건 (§15.7). 낙찰 업체·금액·낙찰률과, 펼치면 참가 업체 점수(개찰 결과).
// participants=null은 '아직 불러오지 않음'이다(0곳과 구분).
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import type { CompetitionAward } from '@/api/competitors'
import UiBadge from '@/components/ui/UiBadge.vue'
import { copy } from '@/copy'
import { formatDate, formatMoney, formatPct } from '@/utils/format'

const props = defineProps<{ award: CompetitionAward; usBizno: string | null; open?: boolean }>()
const expanded = ref(!!props.open)
const score = (v: number | null | undefined) => (v === null || v === undefined ? '–' : formatPct(v))
const pct = (v: number | null | undefined) => (v === null || v === undefined ? copy.competitors.noValue : `${formatPct(v)}%`)
</script>

<template>
  <article class="flex flex-col gap-2 border-t border-border py-3 first:border-t-0" :data-award="award.bid_ntce_no">
    <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <RouterLink v-if="award.bid_id" :to="`/bids/${award.bid_id}`" class="font-medium text-primary hover:underline">
        {{ award.title }}
      </RouterLink>
      <span v-else class="font-medium">{{ award.title }}</span>
      <span class="text-sm tabular text-text-3">{{ formatDate(award.registered_at) }}</span>
      <UiBadge v-if="award.us_participated" tone="primary">{{ copy.competition.usParticipated }}</UiBadge>
      <UiBadge v-if="award.is_joint" tone="neutral">{{ copy.competition.joint }}</UiBadge>
    </div>
    <dl class="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
      <div>
        <dt class="text-text-3">{{ copy.competition.winner }}</dt>
        <dd class="truncate">
          <RouterLink
            v-if="award.bizno && award.bizno !== usBizno"
            :to="`/competitors/${award.bizno}`"
            class="text-primary hover:underline"
          >{{ award.winner_name ?? award.bizno }}</RouterLink>
          <span v-else>{{ award.winner_name ?? copy.competitors.noValue }}</span>
          <UiBadge v-if="award.bizno && award.bizno === usBizno" tone="success" class="ml-1">{{ copy.competition.us }}</UiBadge>
        </dd>
      </div>
      <div>
        <dt class="text-text-3">{{ copy.awards.colAmount }}</dt>
        <dd class="tabular">{{ formatMoney(award.award_amount) }}</dd>
      </div>
      <div>
        <dt class="text-text-3">{{ copy.competition.rateG2b }}</dt>
        <dd class="tabular">{{ pct(award.g2b_award_rate) }}</dd>
      </div>
      <div>
        <dt class="text-text-3">{{ copy.competition.ratio }}</dt>
        <dd class="tabular">{{ award.award_ratio === null ? copy.competitors.noValue : `${formatPct(award.award_ratio * 100)}%` }}</dd>
      </div>
    </dl>

    <p v-if="award.participants === null" class="text-sm text-text-3">{{ copy.competition.notLoaded }}</p>
    <template v-else>
      <button
        type="button"
        class="self-start text-sm font-medium text-primary-hover hover:underline"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        {{ expanded ? copy.competition.hideParticipants : copy.competition.showParticipants }}
        <span class="text-text-3">· {{ copy.competition.participants(award.participants.length) }}</span>
      </button>
      <p v-if="expanded && !award.participants.length" class="text-sm text-text-3">{{ copy.competition.noParticipants }}</p>
      <div v-else-if="expanded" class="overflow-x-auto">
        <table class="w-full min-w-[560px] text-sm" data-participants>
          <thead class="bg-surface-2 text-left text-text-2">
            <tr>
              <th scope="col" class="w-14 px-2 py-1.5 text-right">{{ copy.competition.colRank }}</th>
              <th scope="col" class="px-2 py-1.5">{{ copy.competition.colCompany }}</th>
              <th scope="col" class="px-2 py-1.5 text-right">{{ copy.competition.colBid }}</th>
              <th scope="col" class="px-2 py-1.5 text-right">{{ copy.competition.colTech }}</th>
              <th scope="col" class="px-2 py-1.5 text-right">{{ copy.competition.colPrice }}</th>
              <th scope="col" class="px-2 py-1.5 text-right">{{ copy.competition.colTotal }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="p in award.participants"
              :key="p.bizno"
              class="border-t border-border"
              :class="{ 'bg-primary-soft': p.is_us }"
              :data-us="p.is_us || undefined"
            >
              <td class="px-2 py-1.5 text-right tabular">{{ p.rank ?? '–' }}</td>
              <td class="px-2 py-1.5">
                {{ p.name ?? p.bizno }}
                <UiBadge v-if="p.is_winner" tone="success" class="ml-1">{{ copy.competition.winner }}</UiBadge>
                <UiBadge v-if="p.is_us" tone="primary" class="ml-1">{{ copy.competition.us }}</UiBadge>
                <span v-if="p.rank == null && p.remark" class="block text-xs text-warning-fg" data-remark>{{ p.remark }}</span>
              </td>
              <td class="px-2 py-1.5 text-right tabular">{{ formatMoney(p.bid_amount) }}</td>
              <td class="px-2 py-1.5 text-right tabular">{{ score(p.tech_score) }}</td>
              <td class="px-2 py-1.5 text-right tabular">{{ score(p.price_score) }}</td>
              <td class="px-2 py-1.5 text-right font-medium tabular">{{ score(p.total_score) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </article>
</template>

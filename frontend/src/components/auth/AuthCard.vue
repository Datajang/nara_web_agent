<script setup lang="ts">
// 인증 화면 공통 틀 (SPEC §7.10, B안 2026-11-17): 왼쪽 남색 패널 + 오른쪽 흰 본문.
// 왼쪽은 서비스 소개(intro) 또는 가입 3단계(steps, step = 지금 단계, 4면 모두 끝남).
// 좁은 화면(lg 미만)에서는 왼쪽 패널을 숨기고 본문 위에 브랜드만 보인다.
import { CircleAlert, CircleCheck, Clock, FileText, Mail, Search, Target, Check } from 'lucide-vue-next'
import { computed } from 'vue'
import BrandMark from '@/components/layout/BrandMark.vue'
import { copy } from '@/copy'

const props = withDefaults(
  defineProps<{
    title: string
    subtitle?: string
    aside?: 'intro' | 'steps'
    step?: 1 | 2 | 3 | 4
    icon?: 'mail' | 'clock' | 'check' | 'alert'
  }>(),
  { subtitle: undefined, aside: 'intro', step: 1, icon: undefined },
)

const FEATURE_ICONS = { search: Search, recommend: Target, analyze: FileText } as const

const iconView = computed(() => {
  switch (props.icon) {
    case 'mail':
      return { is: Mail, tone: 'bg-primary-soft text-primary' }
    case 'clock':
      return { is: Clock, tone: 'bg-warning-bg text-warning-fg' }
    case 'check':
      return { is: CircleCheck, tone: 'bg-success-bg text-success-fg' }
    case 'alert':
      return { is: CircleAlert, tone: 'bg-danger-bg text-danger-fg' }
    default:
      return null
  }
})

const steps = computed(() =>
  copy.auth.steps.map((label, i) => {
    const n = i + 1
    return { n, label, done: n < props.step, current: n === props.step }
  }),
)
</script>

<template>
  <div class="flex min-h-screen bg-surface">
    <aside
      class="hidden w-[440px] shrink-0 flex-col justify-between gap-12 bg-primary px-14 pb-12 pt-14 text-white lg:flex"
    >
      <p class="flex items-center gap-2.5 text-lg font-bold tracking-tight">
        <BrandMark />{{ copy.app.name }}
      </p>

      <div v-if="aside === 'intro'" class="flex flex-col gap-9">
        <p class="text-[32px] font-bold leading-[44px] tracking-tight">
          <span v-for="line in copy.auth.introHeadline" :key="line" class="block">{{ line }}</span>
        </p>
        <ul class="flex flex-col gap-5">
          <li v-for="f in copy.auth.introFeatures" :key="f.key" class="flex items-start gap-3.5">
            <span class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-white/12">
              <component :is="FEATURE_ICONS[f.key]" class="size-5" aria-hidden="true" />
            </span>
            <span class="flex flex-col gap-0.5">
              <strong class="text-md font-semibold">{{ f.title }}</strong>
              <span class="text-base text-on-primary-2">{{ f.body }}</span>
            </span>
          </li>
        </ul>
      </div>

      <div v-else class="flex flex-col gap-7">
        <p class="text-[32px] font-bold leading-[44px] tracking-tight">
          <span v-for="line in copy.auth.stepsHeadline" :key="line" class="block">{{ line }}</span>
        </p>
        <ol class="flex flex-col gap-4.5" :aria-label="copy.auth.stepsLabel">
          <li
            v-for="s in steps"
            :key="s.n"
            class="flex items-center gap-3.5 text-md"
            :aria-current="s.current ? 'step' : undefined"
          >
            <span
              v-if="s.done"
              class="flex size-8 shrink-0 items-center justify-center rounded-full bg-white/18"
            >
              <Check class="size-4" :stroke-width="2.6" aria-hidden="true" />
              <span class="sr-only">{{ copy.auth.stepDone }}</span>
            </span>
            <span
              v-else
              class="flex size-8 shrink-0 items-center justify-center rounded-full text-base font-bold"
              :class="s.current ? 'bg-white text-primary' : 'border-[1.5px] border-white/60'"
            >{{ s.n }}</span>
            <span :class="s.current ? 'font-semibold' : 'text-on-primary-2'">{{ s.label }}</span>
            <span v-if="s.current" class="sr-only">{{ copy.auth.stepCurrent }}</span>
          </li>
        </ol>
      </div>

      <p class="text-sm text-on-primary-3">{{ copy.auth.internalOnly }}</p>
    </aside>

    <main id="main" class="flex min-w-0 flex-1 items-start justify-center px-4 py-12 sm:items-center sm:px-6">
      <div class="w-full max-w-[400px]">
        <p class="mb-10 flex items-center gap-2.5 text-lg font-bold tracking-tight text-text lg:hidden">
          <BrandMark />{{ copy.app.name }}
        </p>
        <span
          v-if="iconView"
          class="mb-5 flex size-14 items-center justify-center rounded-xl"
          :class="iconView.tone"
        >
          <component :is="iconView.is" class="size-7" :stroke-width="1.8" aria-hidden="true" />
        </span>
        <h1 class="text-[28px] font-bold leading-9 tracking-tight text-text">{{ title }}</h1>
        <div v-if="subtitle || $slots.subtitle" class="mt-2.5 text-md text-text-2">
          <slot name="subtitle">{{ subtitle }}</slot>
        </div>
        <div v-if="$slots.default" class="mt-8"><slot /></div>
        <nav
          v-if="$slots.footer"
          class="mt-7 flex flex-col gap-2 border-t border-border pt-6 text-md text-text-2"
        >
          <slot name="footer" />
        </nav>
      </div>
    </main>
  </div>
</template>

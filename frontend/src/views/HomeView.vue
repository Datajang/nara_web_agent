<script setup lang="ts">
// 관심 공고 홈 (SPEC §13 P6). 팀·개인 키워드에 맞는 진행 중 공고를 마감 임박 순으로. DB만 읽는다.
// 키워드가 3개 미만이면 키워드 설정으로 보낸다.
import { Pencil } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { feedApi, type FeedItem } from '@/api/teams'
import BidCard from '@/components/bid/BidCard.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useBookmarkToggle } from '@/composables/useBookmarkToggle'
import { copy } from '@/copy'

const PAGE = 20
const router = useRouter()
const keywords = ref<string[]>([])
const items = ref<FeedItem[]>([])
const total = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const failed = ref(false)

async function load(offset = 0) {
  try {
    const f = await feedApi.get(offset, PAGE)
    if (f.needs_keywords) {
      await router.replace('/onboarding')
      return
    }
    keywords.value = f.keywords
    total.value = f.total
    items.value = offset ? [...items.value, ...f.items] : f.items
  } catch {
    failed.value = true
  }
}

onMounted(async () => {
  await load()
  loading.value = false
})

async function more() {
  loadingMore.value = true
  await load(items.value.length)
  loadingMore.value = false
}

const toggleBookmark = useBookmarkToggle(items)
</script>

<template>
  <div class="flex flex-col gap-5">
    <section class="flex flex-col gap-3">
      <p class="text-md text-text-2">{{ copy.feed.lead }}</p>
      <div v-if="keywords.length" class="flex flex-wrap items-center gap-2">
        <span class="text-sm text-text-3">{{ copy.feed.keywords }}</span>
        <span
          v-for="k in keywords"
          :key="k"
          class="inline-flex h-7 items-center rounded-full bg-primary-soft px-3 text-sm text-primary-hover"
        >{{ k }}</span>
        <RouterLink
          to="/onboarding"
          class="inline-flex h-7 items-center gap-1 rounded-full px-2 text-sm text-text-2 hover:bg-surface-2 hover:text-text"
        >
          <Pencil class="size-3.5" aria-hidden="true" />{{ copy.feed.editKeywords }}
        </RouterLink>
      </div>
    </section>

    <div v-if="loading" class="grid gap-3">
      <UiSkeleton v-for="i in 3" :key="i" class="h-28" />
    </div>
    <p v-else-if="failed" class="text-danger-fg">{{ copy.feed.failed }}</p>
    <EmptyState v-else-if="!items.length" :title="copy.feed.empty" />
    <template v-else>
      <p class="text-sm text-text-3">{{ copy.feed.total(total) }}</p>
      <ul class="grid gap-3">
        <li v-for="b in items" :key="b.bid_id" class="flex flex-col gap-1.5">
          <BidCard :bid="b" @toggle-bookmark="toggleBookmark" />
          <p class="flex flex-wrap items-center gap-1.5 px-1 text-xs text-text-3">
            <span>{{ copy.feed.matched }}</span>
            <span
              v-for="k in b.matched_keywords"
              :key="k"
              data-matched
              class="rounded-full bg-surface-2 px-2 py-0.5 text-text-2"
            >{{ k }}</span>
          </p>
        </li>
      </ul>
      <UiButton v-if="items.length < total" variant="secondary" :loading="loadingMore" @click="more">
        {{ copy.feed.more }}
      </UiButton>
    </template>
  </div>
</template>

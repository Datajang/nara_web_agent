<script setup lang="ts">
// AI 어시스턴트 (SPEC §7.6). 좌측 대화 목록, 우측 대화창. 토큰 스트리밍, 인라인 카드, 액션은 버튼으로.
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { MessageSquarePlus, Trash2 } from 'lucide-vue-next'
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { assistantApi } from '@/api/assistant'
import { profilesApi } from '@/api/profiles'
import type { BidCard, StreamEvent } from '@/api/types'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import ChatMessage, { type ChatAction } from '@/components/chat/ChatMessage.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiModal from '@/components/ui/UiModal.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import { useSse } from '@/composables/useSse'
import { copy } from '@/copy'
import { useUiStore } from '@/stores/ui'
import { generalMessage } from '@/utils/authErrors'

const MAX_MESSAGES = 200
const TAB_PATHS: Record<string, string> = {
  search: '/search',
  recommend: '/recommend',
  library: '/library',
  settings: '/settings/profiles',
}

interface Msg {
  key: number
  role: 'user' | 'assistant'
  content: string
  cards: BidCard[]
  actions: ChatAction[]
  error: string | null
  status: string | null
}

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const queryClient = useQueryClient()
const convId = computed(() => (route.params.conversationId ? Number(route.params.conversationId) : null))
const conversations = useQuery({ queryKey: ['conversations'], queryFn: () => assistantApi.list() })
const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => profilesApi.list() })
const current = computed(() => conversations.data.value?.items.find((c) => c.id === convId.value))

const messages = ref<Msg[]>([])
const draft = ref('')
const sse = useSse<StreamEvent>()
const listEl = ref<HTMLElement | null>(null)
const removing = ref(false)
let seq = 0
let skipReload = false

// ---------- 프로필 ----------
const profileChoice = ref<number | null>(null)
const defaultProfile = computed(() => {
  const items = profiles.data.value?.items ?? []
  return (items.find((p) => p.is_default) ?? items[0])?.id ?? null
})
watch(
  [current, defaultProfile],
  () => {
    profileChoice.value = current.value ? current.value.profile_id : defaultProfile.value
  },
  { immediate: true },
)
const profileOptions = computed(() => [
  { value: null as number | null, label: copy.assistant.noProfile },
  ...(profiles.data.value?.items ?? []).map((p) => ({ value: p.id as number | null, label: p.name })),
])
async function changeProfile(v: number | null) {
  profileChoice.value = v
  if (!convId.value) return
  try {
    await assistantApi.update(convId.value, { profile_id: v })
    void queryClient.invalidateQueries({ queryKey: ['conversations'] })
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  }
}
const profileModel = computed({ get: () => profileChoice.value, set: (v) => void changeProfile(v) })

// ---------- 메시지 ----------
async function load(id: number | null) {
  if (skipReload) {
    skipReload = false
    return
  }
  sse.abort()
  messages.value = []
  if (!id) return
  try {
    const res = await assistantApi.messages(id)
    messages.value = res.items.map((m) => ({
      key: ++seq,
      role: m.role,
      content: m.content,
      cards: m.cards,
      actions: [],
      error: null,
      status: null,
    }))
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  }
}
watch(convId, (id) => void load(id), { immediate: true })

function scrollDown() {
  void nextTick(() => listEl.value?.scrollTo?.({ top: listEl.value.scrollHeight }))
}

function errorText(code: string, message: string): string {
  if (code === 'llm_unavailable') return copy.llm.unavailable
  if (code === 'stream_interrupted') return copy.common.streamInterrupted
  return message || copy.common.unknownError
}

async function stream(id: number, content: string) {
  const reply: Msg = {
    key: ++seq,
    role: 'assistant',
    content: '',
    cards: [],
    actions: [],
    error: null,
    status: null,
  }
  messages.value.push(reply)
  const msg = messages.value[messages.value.length - 1]! // 반응형 프록시로 다시 잡는다
  let seen = 0
  const stop = watch(
    () => sse.events.value.length,
    (n) => {
      for (const ev of sse.events.value.slice(seen, n)) {
        if (ev.type === 'token') msg.content += ev.text
        else if (ev.type === 'status') msg.status = ev.message
        else if (ev.type === 'cards') msg.cards = ev.items
        else if (ev.type === 'action') msg.actions.push({ name: ev.name, params: ev.params })
        else if (ev.type === 'error') msg.error = errorText(ev.code, ev.message)
      }
      seen = n
      scrollDown()
    },
  )
  await sse.start(`/conversations/${id}/messages`, { content })
  stop()
  for (const ev of sse.events.value.slice(seen)) {
    if (ev.type === 'token') msg.content += ev.text
    else if (ev.type === 'cards') msg.cards = ev.items
    else if (ev.type === 'action') msg.actions.push({ name: ev.name, params: ev.params })
  }
  if (sse.error.value && !msg.error) msg.error = errorText(sse.error.value.code, '')
  msg.status = null
  void queryClient.invalidateQueries({ queryKey: ['conversations'] })
}

async function send(content: string) {
  let id = convId.value
  if (!id) {
    try {
      const conv = await assistantApi.create(profileChoice.value)
      id = conv.id
      skipReload = true
      await queryClient.invalidateQueries({ queryKey: ['conversations'] })
      await router.push(`/assistant/${id}`)
    } catch (e) {
      ui.toast(generalMessage(e), 'danger')
      return
    }
  }
  messages.value.push({ key: ++seq, role: 'user', content, cards: [], actions: [], error: null, status: null })
  scrollDown()
  await stream(id, content)
}

async function retry(index: number) {
  const prev = messages.value.slice(0, index).reverse().find((m) => m.role === 'user')
  if (!prev || !convId.value) return
  messages.value.splice(index, 1) // 실패한 답만 지우고 같은 질문을 다시 보낸다
  await stream(convId.value, prev.content)
}

function stopStream() {
  sse.abort()
  ui.toast(copy.assistant.stopped)
}

function runAction(a: ChatAction) {
  const tab = String(a.params.tab ?? 'search')
  const path = TAB_PATHS[tab] ?? '/search'
  const query: Record<string, string> = { prefill: '1' } // 이동만 하고 자동 실행은 하지 않는다
  const kws = a.params.keywords
  if (Array.isArray(kws) && kws.length) query.q = kws.map(String).join(',')
  for (const k of ['days', 'source', 'status', 'match', 'sort']) {
    if (a.params[k] != null) query[k] = String(a.params[k])
  }
  void router.push({ path, query: tab === 'search' ? query : {} })
}

async function removeConversation() {
  if (!convId.value) return
  try {
    await assistantApi.remove(convId.value)
    removing.value = false
    await queryClient.invalidateQueries({ queryKey: ['conversations'] })
    await router.push('/assistant')
  } catch (e) {
    ui.toast(generalMessage(e), 'danger')
  }
}

const tooLong = computed(() => messages.value.length >= MAX_MESSAGES)
</script>

<template>
  <div class="grid gap-4 md:grid-cols-[280px_1fr]">
    <aside class="flex flex-col gap-2" :aria-label="copy.assistant.listLabel">
      <RouterLink
        to="/assistant"
        class="inline-flex h-10 items-center justify-center gap-2 rounded-control border border-border-input bg-surface font-medium hover:bg-surface-2"
      >
        <MessageSquarePlus class="size-4" aria-hidden="true" />{{ copy.assistant.newChat }}
      </RouterLink>
      <p v-if="conversations.data.value && !conversations.data.value.items.length" class="px-2 text-sm text-text-3">
        {{ copy.assistant.emptyList }}
      </p>
      <ul class="flex flex-col gap-1">
        <li v-for="c in conversations.data.value?.items ?? []" :key="c.id">
          <RouterLink
            :to="`/assistant/${c.id}`"
            class="block truncate rounded-control px-3 py-2 text-base text-text-2 hover:bg-surface-2"
            :class="c.id === convId ? 'bg-primary-soft text-primary-hover' : ''"
            :aria-current="c.id === convId ? 'page' : undefined"
          >{{ c.title || copy.assistant.untitled }}</RouterLink>
        </li>
      </ul>
    </aside>

    <section class="flex min-h-[60vh] min-w-0 flex-col rounded-card border border-border bg-surface">
      <div class="flex flex-wrap items-center gap-2 border-b border-border p-3">
        <div class="w-56">
          <UiSelect v-model="profileModel" :label="copy.assistant.profile" hide-label :options="profileOptions" />
        </div>
        <UiButton v-if="convId" variant="ghost" size="sm" class="ml-auto" @click="removing = true">
          <Trash2 class="size-4" aria-hidden="true" />{{ copy.assistant.remove }}
        </UiButton>
      </div>

      <div ref="listEl" class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4" aria-live="polite">
        <div v-if="!messages.length" class="flex flex-col items-center gap-3 py-10 text-center">
          <p class="text-lg font-semibold">{{ copy.assistant.emptyTitle }}</p>
          <p class="text-base text-text-2">{{ copy.assistant.emptyBody }}</p>
          <div class="flex flex-wrap justify-center gap-2">
            <button
              v-for="s in copy.assistant.suggestions"
              :key="s"
              type="button"
              class="h-9 rounded-control border border-border-input px-3 text-sm hover:bg-surface-2"
              @click="send(s)"
            >{{ s }}</button>
          </div>
        </div>
        <ChatMessage
          v-for="(m, i) in messages"
          :key="m.key"
          :role="m.role"
          :content="m.content"
          :cards="m.cards"
          :actions="m.actions"
          :error="m.error"
          :status="m.status"
          :streaming="sse.streaming.value && i === messages.length - 1 && m.role === 'assistant'"
          @action="runAction"
          @retry="retry(i)"
        />
      </div>

      <div class="border-t border-border p-3">
        <p v-if="tooLong" class="mb-2 text-sm text-warning-fg">{{ copy.assistant.tooLong }}</p>
        <ChatComposer v-model="draft" :streaming="sse.streaming.value" @send="send" @stop="stopStream" />
      </div>
    </section>

    <UiModal v-model:open="removing" :title="copy.admin.confirmTitle" :description="copy.assistant.confirmRemove">
      <template #actions>
        <UiButton variant="ghost" @click="removing = false">{{ copy.common.cancel }}</UiButton>
        <UiButton variant="danger" @click="removeConversation">{{ copy.common.confirm }}</UiButton>
      </template>
    </UiModal>
  </div>
</template>

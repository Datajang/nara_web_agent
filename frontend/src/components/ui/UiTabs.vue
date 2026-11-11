<script setup lang="ts" generic="T extends string">
// 탭 (SPEC §10.4). 선택 상태는 호출하는 화면이 URL 쿼리와 동기화한다. 화살표 키 이동은 Reka가 맡는다.
import { TabsList, TabsRoot, TabsTrigger } from 'reka-ui'

defineProps<{ items: Array<{ value: T; label: string }>; label: string }>()
const model = defineModel<T>({ required: true })
</script>

<template>
  <TabsRoot v-model="model">
    <TabsList :aria-label="label" class="flex gap-1 border-b border-border">
      <TabsTrigger
        v-for="item in items"
        :key="item.value"
        :value="item.value"
        class="-mb-px h-10 border-b-2 border-transparent px-3 text-base font-medium text-text-2 hover:text-text data-[state=active]:border-primary data-[state=active]:text-primary-hover"
      >
        {{ item.label }}
      </TabsTrigger>
    </TabsList>
    <slot />
  </TabsRoot>
</template>

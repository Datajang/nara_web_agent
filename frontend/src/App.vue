<script setup lang="ts">
import { RouterView } from 'vue-router'
import ResultMailNotice from '@/components/bid/ResultMailNotice.vue'
import UiToast from '@/components/ui/UiToast.vue'
</script>

<template>
  <RouterView />
  <UiToast />
  <ResultMailNotice />
</template>

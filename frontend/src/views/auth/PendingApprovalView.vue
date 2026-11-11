<script setup lang="ts">
import { RouterLink } from 'vue-router'
import AuthCard from '@/components/auth/AuthCard.vue'
import { copy } from '@/copy'
</script>

<template>
  <AuthCard :title="copy.auth.pendingApprovalTitle" :subtitle="copy.auth.pendingApprovalBody">
    <template #footer>
      <RouterLink class="text-primary hover:underline" to="/login">{{ copy.auth.toLogin }}</RouterLink>
    </template>
  </AuthCard>
</template>

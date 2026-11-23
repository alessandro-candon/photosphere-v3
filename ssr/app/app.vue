<template>
  <NuxtLayout>
    <NuxtPage />
  </NuxtLayout>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { storeToRefs } from 'pinia'
import { navigateTo, useRoute } from '#imports'
import { useAuthStore } from './stores/auth'

const route = useRoute()
const authStore = useAuthStore()
const { initialized, isAuthenticated } = storeToRefs(authStore)

watch(
  [initialized, isAuthenticated, () => route.path],
  async ([isInit, isAuthed, path]) => {
    if (!import.meta.client || !isInit) return
    if (!isAuthed && path !== '/login') {
      await navigateTo('/login')
    } else if (isAuthed && path === '/login') {
      await navigateTo('/')
    }
  },
  { immediate: true }
)
</script>

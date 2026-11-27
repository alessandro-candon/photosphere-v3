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
  [initialized, isAuthenticated],
  async ([isInit, isAuthed]) => {
    if (!import.meta.client || !isInit) return
    if (!isAuthed && route.path !== '/login') {
      await navigateTo('/login')
    } else if (isAuthed && route.path === '/login') {
      await navigateTo('/')
    }
  },
  { immediate: true }
)
</script>

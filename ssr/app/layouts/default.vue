<template>
  <AppShell
    :authenticated="isAuthenticated"
    :user-email="userEmail"
    :current-path="route.path"
    :theme="theme"
    @logout="logout"
    @toggle-theme="authStore.toggleTheme"
  >
    <slot />
  </AppShell>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useRoute } from '#imports'
import AppShell from '../components/organisms/AppShell.vue'
import { useFirebaseAuth } from '../composables/useFirebaseAuth'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const authStore = useAuthStore()
const { theme } = storeToRefs(authStore)
const { isAuthenticated, userEmail, logout } = useFirebaseAuth()
</script>

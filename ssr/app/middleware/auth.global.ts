import { storeToRefs } from 'pinia'
import { defineNuxtRouteMiddleware, navigateTo } from '#imports'
import { useAuthStore } from '../stores/auth'

export default defineNuxtRouteMiddleware((to) => {
  if (import.meta.server) {
    return
  }

  const authStore = useAuthStore()
  const { isAuthenticated, initialized } = storeToRefs(authStore)

  if (!initialized.value) {
    return
  }

  if (!isAuthenticated.value && to.path !== '/login') {
    return navigateTo('/login')
  }

  if (isAuthenticated.value && to.path === '/login') {
    return navigateTo('/')
  }
})

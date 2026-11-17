import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useRuntimeConfig } from '#imports'

export interface ClientUser {
  uid: string
  email: string | null
  displayName: string | null
  photoURL: string | null
}

const LANG_STORAGE_KEY = 'photosphere_preferred_lang'

export const useAuthStore = defineStore('auth', () => {
  const runtimeConfig = useRuntimeConfig()
  const user = ref<ClientUser | null>(null)
  const idToken = ref<string | null>(null)
  const loading = ref(false)
  const initialized = ref(false)

  const initialLang =
    import.meta.client && typeof localStorage !== 'undefined'
      ? localStorage.getItem(LANG_STORAGE_KEY) || runtimeConfig.public.defaultLang || 'en'
      : runtimeConfig.public.defaultLang || 'en'

  const preferredLang = ref<string>(initialLang)

  const isAuthenticated = computed(() => Boolean(user.value && idToken.value))
  const userEmail = computed(() => user.value?.email || null)

  const setSession = (nextUser: ClientUser | null, nextToken: string | null) => {
    user.value = nextUser
    idToken.value = nextToken
  }

  const setLoading = (value: boolean) => {
    loading.value = value
  }

  const setInitialized = (value: boolean) => {
    initialized.value = value
  }

  const setPreferredLang = (lang: string) => {
    const clean = lang.trim().toLowerCase() || 'en'
    preferredLang.value = clean
    if (import.meta.client && typeof localStorage !== 'undefined') {
      localStorage.setItem(LANG_STORAGE_KEY, clean)
    }
  }

  const clearSession = () => {
    user.value = null
    idToken.value = null
  }

  return {
    user,
    idToken,
    loading,
    initialized,
    preferredLang,
    isAuthenticated,
    userEmail,
    setSession,
    setLoading,
    setInitialized,
    setPreferredLang,
    clearSession,
  }
})

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useRuntimeConfig } from '#imports'

export interface ClientUser {
  uid: string
  email: string | null
  displayName: string | null
  photoURL: string | null
}

export type ThemeMode = 'light' | 'dark'

const LANG_STORAGE_KEY = 'photosphere_preferred_lang'
const THEME_STORAGE_KEY = 'photosphere_theme'

const applyThemeClass = (mode: ThemeMode): void => {
  if (!import.meta.client || typeof document === 'undefined') {
    return
  }
  if (mode === 'dark') {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}

const resolveInitialTheme = (): ThemeMode => {
  if (!import.meta.client) {
    return 'dark'
  }
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') {
      return stored
    }
    if (
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-color-scheme: dark)').matches
    ) {
      return 'dark'
    }
    return 'light'
  } catch {
    return 'dark'
  }
}

export const useAuthStore = defineStore('auth', () => {
  const runtimeConfig = useRuntimeConfig()
  const user = ref<ClientUser | null>(null)
  const idToken = ref<string | null>(null)
  const loading = ref(false)
  const initialized = ref(false)
  const isAdmin = ref(false)
  const canEditAlbums = ref(false)

  const initialLang =
    import.meta.client && typeof localStorage !== 'undefined'
      ? localStorage.getItem(LANG_STORAGE_KEY) || runtimeConfig.public.defaultLang || 'en'
      : runtimeConfig.public.defaultLang || 'en'

  const preferredLang = ref<string>(initialLang)
  const theme = ref<ThemeMode>(resolveInitialTheme())

  const isAuthenticated = computed(() => Boolean(user.value && idToken.value))
  const userEmail = computed(() => user.value?.email || null)

  const setSession = (nextUser: ClientUser | null, nextToken: string | null) => {
    user.value = nextUser
    idToken.value = nextToken
  }

  const setCapabilities = (caps: { isAdmin: boolean; canEditAlbums: boolean }) => {
    isAdmin.value = caps.isAdmin
    canEditAlbums.value = caps.canEditAlbums
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

  const setTheme = (mode: ThemeMode) => {
    theme.value = mode
    applyThemeClass(mode)
    if (import.meta.client && typeof localStorage !== 'undefined') {
      localStorage.setItem(THEME_STORAGE_KEY, mode)
    }
  }

  const toggleTheme = () => {
    setTheme(theme.value === 'dark' ? 'light' : 'dark')
  }

  const clearSession = () => {
    user.value = null
    idToken.value = null
    isAdmin.value = false
    canEditAlbums.value = false
  }

  return {
    user,
    idToken,
    loading,
    initialized,
    isAdmin,
    canEditAlbums,
    preferredLang,
    theme,
    isAuthenticated,
    userEmail,
    setSession,
    setCapabilities,
    setLoading,
    setInitialized,
    setPreferredLang,
    setTheme,
    toggleTheme,
    clearSession,
  }
})

import { getApps, initializeApp } from 'firebase/app'
import { getAuth, onIdTokenChanged, type Auth } from 'firebase/auth'
import { defineNuxtPlugin, useRuntimeConfig } from '#imports'
import { usePhotosphereApi } from '../composables/usePhotosphereApi'
import { useAuthStore } from '../stores/auth'

export default defineNuxtPlugin(() => {
  const runtimeConfig = useRuntimeConfig()
  const fbConfig = runtimeConfig.public.firebase
  const authStore = useAuthStore()
  const { bootstrapSession, clearMediaSession } = usePhotosphereApi()

  if (!fbConfig?.apiKey || !fbConfig?.projectId) {
    authStore.setInitialized(true)
    return {
      provide: {
        firebaseAuth: null as Auth | null,
      },
    }
  }

  const app = getApps().length > 0 ? getApps()[0]! : initializeApp(fbConfig)
  const auth = getAuth(app)

  onIdTokenChanged(auth, async (firebaseUser) => {
    if (firebaseUser) {
      try {
        const token = await firebaseUser.getIdToken()
        authStore.setSession(
          {
            uid: firebaseUser.uid,
            email: firebaseUser.email,
            displayName: firebaseUser.displayName,
            photoURL: firebaseUser.photoURL,
          },
          token
        )
        await bootstrapSession(token)
      } catch {
        // Non-allowlisted or revoked user; clear session cleanly
        authStore.clearSession()
        await clearMediaSession().catch(() => {})
      }
    } else {
      authStore.clearSession()
      await clearMediaSession().catch(() => {})
    }
    authStore.setInitialized(true)
  })

  return {
    provide: {
      firebaseAuth: auth as Auth | null,
    },
  }
})

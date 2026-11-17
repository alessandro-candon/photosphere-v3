import { getApps, initializeApp } from 'firebase/app'
import { getAuth, onIdTokenChanged, type Auth } from 'firebase/auth'
import { defineNuxtPlugin, useRuntimeConfig } from '#imports'
import { useAuthStore } from '../stores/auth'

export default defineNuxtPlugin(() => {
  const runtimeConfig = useRuntimeConfig()
  const fbConfig = runtimeConfig.public.firebase
  const authStore = useAuthStore()

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
    } else {
      authStore.clearSession()
    }
    authStore.setInitialized(true)
  })

  return {
    provide: {
      firebaseAuth: auth as Auth | null,
    },
  }
})

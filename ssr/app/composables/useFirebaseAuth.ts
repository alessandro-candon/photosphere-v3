import { GoogleAuthProvider, signInWithPopup, signOut, type Auth } from 'firebase/auth'
import { storeToRefs } from 'pinia'
import { navigateTo, useNuxtApp } from '#imports'
import { useAuthStore } from '../stores/auth'

export const useFirebaseAuth = () => {
  const nuxtApp = useNuxtApp()
  const authStore = useAuthStore()
  const { user, idToken, loading, isAuthenticated, userEmail } = storeToRefs(authStore)

  const getFirebaseAuth = (): Auth | null => {
    return (nuxtApp.$firebaseAuth as Auth | null | undefined) || null
  }

  const loginWithGoogle = async (): Promise<void> => {
    const auth = getFirebaseAuth()
    if (!auth) {
      throw new Error('Firebase client authentication is not configured')
    }
    authStore.setLoading(true)
    try {
      const provider = new GoogleAuthProvider()
      const credential = await signInWithPopup(auth, provider)
      const token = await credential.user.getIdToken()
      authStore.setSession(
        {
          uid: credential.user.uid,
          email: credential.user.email,
          displayName: credential.user.displayName,
          photoURL: credential.user.photoURL,
        },
        token
      )
      await navigateTo('/')
    } finally {
      authStore.setLoading(false)
    }
  }

  const logout = async (): Promise<void> => {
    const auth = getFirebaseAuth()
    if (auth) {
      await signOut(auth)
    }
    authStore.clearSession()
    await navigateTo('/login')
  }

  const refreshIdToken = async (forceRefresh = true): Promise<string | null> => {
    const auth = getFirebaseAuth()
    if (!auth?.currentUser) {
      return idToken.value
    }
    const freshToken = await auth.currentUser.getIdToken(forceRefresh)
    authStore.setSession(authStore.user, freshToken)
    return freshToken
  }

  return {
    user,
    idToken,
    loading,
    isAuthenticated,
    userEmail,
    loginWithGoogle,
    logout,
    refreshIdToken,
  }
}

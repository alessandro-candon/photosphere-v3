<template>
  <LoginCard :loading="loading" :error="errorMsg" @sign-in="handleLogin" />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import LoginCard from '../components/organisms/LoginCard.vue'
import { useFirebaseAuth } from '../composables/useFirebaseAuth'

const { loginWithGoogle, loading } = useFirebaseAuth()
const errorMsg = ref('')

const handleLogin = async () => {
  errorMsg.value = ''
  try {
    await loginWithGoogle()
  } catch (error) {
    errorMsg.value = error instanceof Error ? error.message : 'Sign-in failed'
  }
}
</script>

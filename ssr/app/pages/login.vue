<template>
  <q-page class="flex flex-center q-pa-md">
    <q-card style="width: 100%; max-width: 420px" class="q-pa-md text-center">
      <q-card-section>
        <q-icon name="photo_library" size="56px" color="primary" />
        <div class="text-h5 q-mt-sm">Photosphere v3</div>
        <div class="text-caption text-grey-7 q-mt-xs">
          Sign in with an authorized Google account to access your private archive.
        </div>
      </q-card-section>

      <q-card-section v-if="errorMsg">
        <q-banner dense class="bg-negative text-white rounded-borders">
          {{ errorMsg }}
        </q-banner>
      </q-card-section>

      <q-card-actions align="center">
        <q-btn
          color="primary"
          icon="login"
          label="Sign in with Google"
          :loading="loading"
          no-caps
          @click="handleLogin"
        />
      </q-card-actions>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import { ref } from 'vue'
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

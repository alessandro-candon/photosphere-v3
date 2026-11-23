<template>
  <div class="flex min-h-[calc(100vh-4rem)] items-center justify-center">
    <Card class="w-full max-w-md p-6 sm:p-8 text-center">
      <div
        class="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground"
      >
        <Camera class="h-6 w-6" />
      </div>

      <h1 class="text-xl sm:text-2xl font-semibold tracking-tight">Photosphere</h1>
      <p class="mt-1.5 text-sm text-muted-foreground">
        Sign in with an allowlisted Google account to browse your photo archive.
      </p>

      <div v-if="error" class="mt-4 text-left">
        <ErrorBanner :message="error" />
      </div>

      <Button class="mt-6 w-full" size="lg" :disabled="loading" @click="emit('sign-in')">
        {{ loading ? 'Signing in...' : 'Sign in with Google' }}
      </Button>
    </Card>
  </div>
</template>

<script setup lang="ts">
import { Camera } from 'lucide-vue-next'
import ErrorBanner from '../common/ErrorBanner.vue'
import Button from '../ui/Button.vue'
import Card from '../ui/Card.vue'

defineProps<{
  loading: boolean
  error: string
}>()

const emit = defineEmits<{
  'sign-in': []
}>()
</script>

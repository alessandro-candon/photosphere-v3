<template>
  <div
    role="alert"
    class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive"
  >
    <div class="flex min-w-0 flex-1 items-start gap-2.5">
      <AlertCircle class="mt-0.5 h-4 w-4 shrink-0" />
      <div class="min-w-0">
        <p class="font-medium">{{ message }}</p>
        <p v-if="requestId" class="mt-0.5 font-mono text-xs opacity-80">
          Request ID: {{ requestId }}
        </p>
      </div>
    </div>
    <Button v-if="retryable" variant="outline" size="sm" @click="emit('retry')"> Retry </Button>
  </div>
</template>

<script setup lang="ts">
import { AlertCircle } from 'lucide-vue-next'
import Button from '../ui/Button.vue'

withDefaults(
  defineProps<{
    message: string
    requestId?: string
    retryable?: boolean
  }>(),
  {
    requestId: undefined,
    retryable: false,
  }
)

const emit = defineEmits<{
  retry: []
}>()
</script>

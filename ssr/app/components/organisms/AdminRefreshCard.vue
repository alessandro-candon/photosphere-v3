<template>
  <SettingsSectionCard
    title="Database Cache (Admin)"
    description="Force a reload of the media index, AI dictionaries, and albums from Google Cloud Storage."
  >
    <div class="space-y-4">
      <div
        v-if="statusMessage"
        role="status"
        class="rounded-lg border border-primary/40 bg-primary/10 px-4 py-3 text-sm text-foreground"
      >
        {{ statusMessage }}
      </div>

      <ErrorBanner v-if="error" :message="error" :request-id="errorRequestId" />

      <div
        v-if="lastResult"
        class="grid grid-cols-2 gap-3 rounded-lg border border-border bg-background p-3 text-xs sm:grid-cols-4"
      >
        <div>
          <p class="text-muted-foreground">Media Records</p>
          <p class="mt-0.5 font-semibold text-foreground">{{ lastResult.totalRecords }}</p>
        </div>
        <div>
          <p class="text-muted-foreground">Albums</p>
          <p class="mt-0.5 font-semibold text-foreground">{{ lastResult.totalAlbums }}</p>
        </div>
        <div>
          <p class="text-muted-foreground">Dictionary Lang</p>
          <p class="mt-0.5 font-mono font-semibold text-foreground">{{ lastResult.lang }}</p>
        </div>
        <div>
          <p class="text-muted-foreground">Refreshed At</p>
          <p class="mt-0.5 font-semibold text-foreground">
            {{ new Date(lastResult.loadedAt).toLocaleTimeString() }}
          </p>
        </div>
      </div>

      <Button :disabled="refreshing" @click="emit('refresh')">
        <RefreshCw :class="['h-4 w-4', refreshing ? 'animate-spin' : '']" />
        <span>{{ refreshing ? 'Refreshing Remote DB...' : 'Refresh Remote DB' }}</span>
      </Button>
    </div>
  </SettingsSectionCard>
</template>

<script setup lang="ts">
import { RefreshCw } from 'lucide-vue-next'
import ErrorBanner from '../common/ErrorBanner.vue'
import Button from '../ui/Button.vue'
import SettingsSectionCard from './SettingsSectionCard.vue'
import type { RefreshDatabaseResponse } from '../../types'

defineProps<{
  refreshing: boolean
  statusMessage: string
  error: string
  errorRequestId?: string
  lastResult: RefreshDatabaseResponse | null
}>()

const emit = defineEmits<{
  refresh: []
}>()
</script>

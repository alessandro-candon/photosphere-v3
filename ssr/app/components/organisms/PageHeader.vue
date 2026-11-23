<template>
  <header class="mb-4 flex flex-wrap items-center justify-between gap-3">
    <div class="flex min-w-0 items-center gap-2.5">
      <NuxtLink
        v-if="backTo"
        :to="backTo"
        aria-label="Go back"
        class="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg border border-border bg-surface text-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <ArrowLeft class="h-4 w-4" />
      </NuxtLink>

      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <h1 class="truncate text-xl sm:text-2xl font-semibold tracking-tight">{{ title }}</h1>
          <Badge v-if="subtitle" variant="outline">{{ subtitle }}</Badge>
        </div>
        <p v-if="description" class="mt-0.5 text-xs sm:text-sm text-muted-foreground">
          {{ description }}
        </p>
      </div>
    </div>

    <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
import { ArrowLeft } from 'lucide-vue-next'
import Badge from '../ui/Badge.vue'

withDefaults(
  defineProps<{
    title: string
    subtitle?: string
    description?: string
    backTo?: string
  }>(),
  {
    subtitle: undefined,
    description: undefined,
    backTo: undefined,
  }
)
</script>

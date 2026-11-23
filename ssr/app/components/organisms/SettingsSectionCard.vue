<template>
  <Card class="p-5">
    <div class="mb-4">
      <h2 class="text-base font-semibold tracking-tight text-foreground">{{ title }}</h2>
      <p v-if="description" class="mt-1 text-sm text-muted-foreground">
        {{ description }}
      </p>
    </div>
    <slot />
  </Card>
</template>

<script setup lang="ts">
import Card from '../ui/Card.vue'

withDefaults(
  defineProps<{
    title: string
    description?: string
  }>(),
  {
    description: undefined,
  }
)
</script>

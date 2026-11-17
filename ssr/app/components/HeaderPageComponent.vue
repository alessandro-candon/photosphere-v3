<template>
  <div class="q-mb-md row items-center justify-between">
    <div>
      <div class="text-h5 text-weight-medium">{{ title }}</div>
      <div v-if="subtitle" class="text-caption text-grey-7">{{ subtitle }}</div>
    </div>
    <slot name="actions" />
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  subtitle?: string
}>()
</script>

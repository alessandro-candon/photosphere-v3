<template>
  <div
    class="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-surface/60 px-6 py-14 text-center"
  >
    <div
      class="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground"
    >
      <component :is="iconComponent" class="h-6 w-6" />
    </div>
    <h2 class="text-base font-semibold text-foreground">{{ title }}</h2>
    <p v-if="description" class="mt-1 max-w-md text-sm text-muted-foreground">
      {{ description }}
    </p>
    <div v-if="$slots.default" class="mt-4">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue'
import { FolderOpen, Heart, Images, Search } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    icon?: 'images' | 'search' | 'folder' | 'heart'
    title: string
    description?: string
  }>(),
  {
    icon: 'images',
    description: undefined,
  }
)

const iconMap: Record<'images' | 'search' | 'folder' | 'heart', Component> = {
  images: Images,
  search: Search,
  folder: FolderOpen,
  heart: Heart,
}

const iconComponent = computed(() => iconMap[props.icon])
</script>

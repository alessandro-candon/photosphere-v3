<template>
  <Button
    variant="ghost"
    :size="showLabel ? 'default' : 'icon'"
    :aria-label="theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'"
    @click="emit('toggle')"
  >
    <Sun v-if="theme === 'dark'" class="h-4 w-4" />
    <Moon v-else class="h-4 w-4" />
    <span v-if="showLabel">{{ theme === 'dark' ? 'Light mode' : 'Dark mode' }}</span>
  </Button>
</template>

<script setup lang="ts">
import { Moon, Sun } from 'lucide-vue-next'
import Button from '../ui/Button.vue'

withDefaults(
  defineProps<{
    theme: 'light' | 'dark'
    showLabel?: boolean
  }>(),
  {
    showLabel: false,
  }
)

const emit = defineEmits<{
  toggle: []
}>()
</script>

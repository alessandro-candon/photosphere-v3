<template>
  <div
    v-if="selectedCount > 0"
    class="fixed inset-x-3 bottom-20 z-40 mx-auto flex max-w-xl items-center justify-between gap-2 rounded-xl border border-border bg-surface-elevated px-4 py-2.5 shadow-lg md:bottom-5"
  >
    <div class="flex items-center gap-2">
      <Badge variant="default">{{ selectedCount }} selected</Badge>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <Button
        v-if="mode === 'gallery'"
        size="sm"
        :disabled="submitting"
        @click="emit('add-to-album')"
      >
        <FolderPlus class="h-4 w-4" />
        <span>Add to Album</span>
      </Button>

      <Button
        v-else
        variant="destructive"
        size="sm"
        :disabled="submitting"
        @click="emit('remove-from-album')"
      >
        <Trash2 class="h-4 w-4" />
        <span>Remove from Album</span>
      </Button>

      <Button variant="ghost" size="sm" :disabled="submitting" @click="emit('clear')">
        <X class="h-4 w-4" />
        <span>Clear</span>
      </Button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { FolderPlus, Trash2, X } from 'lucide-vue-next'
import Badge from '../ui/Badge.vue'
import Button from '../ui/Button.vue'

withDefaults(
  defineProps<{
    selectedCount: number
    mode: 'gallery' | 'album'
    submitting?: boolean
  }>(),
  {
    submitting: false,
  }
)

const emit = defineEmits<{
  'add-to-album': []
  'remove-from-album': []
  clear: []
}>()
</script>

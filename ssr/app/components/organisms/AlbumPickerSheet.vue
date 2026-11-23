<template>
  <Sheet
    :open="open"
    title="Add to Album"
    :description="`Add ${itemCount} selected ${itemCount === 1 ? 'item' : 'items'} to an existing or new album.`"
    @close="emit('close')"
  >
    <div class="space-y-4">
      <ErrorBanner v-if="error" :message="error" />

      <!-- Quick create new album -->
      <form class="flex gap-2" @submit.prevent="submitNewAlbum">
        <Input
          v-model="newAlbumName"
          placeholder="New album name..."
          aria-label="New album name"
          :disabled="submitting"
        />
        <Button type="submit" :disabled="submitting || !newAlbumName.trim()">
          <Plus class="h-4 w-4" />
          <span>Create</span>
        </Button>
      </form>
      <p v-if="localError" class="text-xs text-destructive">{{ localError }}</p>

      <!-- Existing albums list -->
      <div class="space-y-1.5">
        <p class="text-xs font-medium text-muted-foreground">Existing Albums</p>
        <div v-if="loading" class="space-y-2">
          <Skeleton v-for="n in 3" :key="n" class="h-12 w-full rounded-lg" />
        </div>
        <p v-else-if="albums.length === 0" class="py-4 text-center text-sm text-muted-foreground">
          No albums yet. Create one above.
        </p>
        <div v-else class="max-h-64 space-y-1.5 overflow-y-auto">
          <button
            v-for="album in albums"
            :key="album.name"
            type="button"
            :disabled="submitting"
            class="flex min-h-11 w-full items-center justify-between gap-3 rounded-lg border border-border bg-surface px-3 py-2 text-left text-sm hover:bg-muted disabled:opacity-50"
            @click="emit('select-album', album.name)"
          >
            <span class="flex min-w-0 items-center gap-2.5">
              <FolderHeart class="h-4 w-4 shrink-0 text-primary" />
              <span class="truncate font-medium text-foreground">{{ album.name }}</span>
            </span>
            <Badge variant="outline">{{ album.totalFiles }}</Badge>
          </button>
        </div>
      </div>
    </div>
  </Sheet>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { FolderHeart, Plus } from 'lucide-vue-next'
import ErrorBanner from '../common/ErrorBanner.vue'
import Badge from '../ui/Badge.vue'
import Button from '../ui/Button.vue'
import Input from '../ui/Input.vue'
import Sheet from '../ui/Sheet.vue'
import type { AlbumSummary } from '../../types'

const props = defineProps<{
  open: boolean
  albums: AlbumSummary[]
  loading: boolean
  submitting: boolean
  error: string
  itemCount: number
}>()

const emit = defineEmits<{
  'select-album': [albumName: string]
  'create-and-add': [albumName: string]
  close: []
}>()

const newAlbumName = ref('')
const localError = ref('')

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      newAlbumName.value = ''
      localError.value = ''
    }
  }
)

const submitNewAlbum = () => {
  const clean = newAlbumName.value.trim()
  if (!clean) {
    localError.value = 'Enter an album name.'
    return
  }
  if (clean.includes('/') || clean.includes('\\')) {
    localError.value = 'Album name cannot contain slashes.'
    return
  }
  localError.value = ''
  emit('create-and-add', clean)
}
</script>

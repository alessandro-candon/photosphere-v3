<template>
  <div>
    <!-- Initial skeleton grid -->
    <div
      v-if="loading && albums.length === 0"
      class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
      aria-busy="true"
    >
      <Skeleton v-for="n in 8" :key="n" class="h-56 w-full rounded-xl" />
    </div>

    <!-- Album cards -->
    <div
      v-else-if="albums.length > 0"
      class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
    >
      <Card
        v-for="album in albums"
        :key="album.name"
        class="group overflow-hidden transition-shadow hover:shadow-md"
      >
        <button
          type="button"
          class="block w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          @click="emit('open', album.name)"
        >
          <div class="grid aspect-4/3 w-full grid-cols-2 grid-rows-2 gap-0.5 bg-muted">
            <template v-if="album.coverThumbnails.length > 0">
              <div v-for="idx in 4" :key="idx" class="h-full w-full overflow-hidden bg-muted">
                <img
                  v-if="album.coverThumbnails[idx - 1]"
                  :src="album.coverThumbnails[idx - 1]"
                  :alt="`${album.name} preview ${idx}`"
                  loading="lazy"
                  class="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
                />
              </div>
            </template>
            <div
              v-else
              class="col-span-2 row-span-2 flex items-center justify-center text-muted-foreground"
            >
              <FolderHeart class="h-10 w-10" />
            </div>
          </div>
        </button>

        <div class="flex items-center justify-between gap-2 p-3">
          <button
            type="button"
            class="min-w-0 flex-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md"
            @click="emit('open', album.name)"
          >
            <h2 class="truncate text-base font-medium text-foreground">{{ album.name }}</h2>
            <p class="mt-0.5 text-xs text-muted-foreground">
              {{ album.totalFiles }} {{ album.totalFiles === 1 ? 'item' : 'items' }}
            </p>
          </button>

          <div v-if="canEdit" class="flex shrink-0 items-center gap-0.5">
            <Button
              variant="ghost"
              size="icon"
              :aria-label="`Rename ${album.name}`"
              @click="emit('rename', album.name)"
            >
              <Pencil class="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              class="text-destructive hover:text-destructive"
              :aria-label="`Delete ${album.name}`"
              @click="emit('delete', album.name)"
            >
              <Trash2 class="h-4 w-4" />
            </Button>
          </div>
        </div>
      </Card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { FolderHeart, Pencil, Trash2 } from 'lucide-vue-next'
import Button from '../ui/Button.vue'
import Card from '../ui/Card.vue'
import Skeleton from '../ui/Skeleton.vue'
import type { AlbumSummary } from '../../types'

defineProps<{
  albums: AlbumSummary[]
  loading: boolean
  canEdit: boolean
}>()

const emit = defineEmits<{
  open: [name: string]
  rename: [name: string]
  delete: [name: string]
}>()
</script>

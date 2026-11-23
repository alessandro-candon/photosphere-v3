<template>
  <Teleport to="body">
    <div
      v-if="open && item"
      class="fixed inset-0 z-50 flex flex-col bg-scrim text-white backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      :aria-label="`Viewing ${item.fileName}`"
    >
      <!-- Top Bar -->
      <header
        class="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-white/10 bg-black/50 px-3 sm:px-4"
      >
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm font-medium text-white">{{ item.fileName }}</p>
          <p v-if="formattedDate" class="truncate text-xs text-white/70">{{ formattedDate }}</p>
        </div>

        <div class="flex items-center gap-1">
          <Button
            v-if="canEditAlbums"
            variant="ghost"
            size="icon"
            class="text-white hover:bg-white/15 hover:text-white"
            aria-label="Add to album"
            @click="emit('add-to-album', item.hash)"
          >
            <FolderPlus class="h-5 w-5" />
          </Button>

          <a
            :href="item.sourceUrl"
            :download="item.fileName"
            aria-label="Download original file"
            class="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg text-white hover:bg-white/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Download class="h-5 w-5" />
          </a>

          <Button
            variant="ghost"
            size="icon"
            :class="
              showInfo
                ? 'text-white hover:bg-white/15 hover:text-white bg-white/20'
                : 'text-white hover:bg-white/15 hover:text-white'
            "
            aria-label="Toggle media info"
            :aria-expanded="showInfo"
            @click="showInfo = !showInfo"
          >
            <Info class="h-5 w-5" />
          </Button>

          <Button
            variant="ghost"
            size="icon"
            class="text-white hover:bg-white/15 hover:text-white"
            aria-label="Close viewer"
            @click="emit('close')"
          >
            <X class="h-5 w-5" />
          </Button>
        </div>
      </header>

      <!-- Main Stage + Optional Info Drawer -->
      <div class="relative flex min-h-0 flex-1 flex-col md:flex-row">
        <div class="relative flex min-h-0 flex-1 items-center justify-center p-2 sm:p-6">
          <Button
            v-if="hasPrev"
            variant="ghost"
            size="icon"
            class="absolute left-2 top-1/2 z-10 -translate-y-1/2 rounded-full bg-black/50 text-white hover:bg-black/75 hover:text-white"
            aria-label="Previous media item"
            @click="emit('prev')"
          >
            <ChevronLeft class="h-6 w-6" />
          </Button>

          <img
            v-if="item.fileType === 'IMAGE'"
            :key="item.hash"
            :src="item.sourceUrl"
            :alt="detail?.caption || item.fileName"
            class="max-h-full max-w-full object-contain select-none"
          />

          <video
            v-else-if="item.fileType === 'VIDEO'"
            :key="item.hash"
            :src="item.sourceUrl"
            controls
            playsinline
            class="max-h-full max-w-full rounded-md bg-black"
          />

          <div
            v-else
            class="flex flex-col items-center gap-3 rounded-xl border border-white/15 bg-black/50 p-6 text-center"
          >
            <FileText class="h-12 w-12 text-white/80" />
            <p class="text-sm font-medium">{{ item.fileName }}</p>
            <a
              :href="item.sourceUrl"
              :download="item.fileName"
              class="inline-flex min-h-11 items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            >
              <Download class="h-4 w-4" />
              Download File
            </a>
          </div>

          <Button
            v-if="hasNext"
            variant="ghost"
            size="icon"
            class="absolute right-2 top-1/2 z-10 -translate-y-1/2 rounded-full bg-black/50 text-white hover:bg-black/75 hover:text-white"
            aria-label="Next media item"
            @click="emit('next')"
          >
            <ChevronRight class="h-6 w-6" />
          </Button>
        </div>

        <!-- Collapsible Metadata Drawer -->
        <aside
          v-if="showInfo"
          class="max-h-[45vh] md:max-h-none md:w-80 lg:w-96 shrink-0 overflow-y-auto border-t md:border-t-0 md:border-l border-border bg-surface text-foreground p-4 space-y-4"
        >
          <h3 class="text-base font-semibold tracking-tight">Details</h3>

          <div v-if="detailLoading" class="space-y-3">
            <Skeleton class="h-4 w-3/4" />
            <Skeleton class="h-4 w-1/2" />
            <Skeleton class="h-16 w-full" />
          </div>

          <div v-else class="space-y-4 text-sm">
            <div>
              <p class="text-xs text-muted-foreground">Filename</p>
              <p class="mt-0.5 break-all font-medium">{{ item.fileName }}</p>
            </div>

            <div v-if="formattedDate">
              <p class="text-xs text-muted-foreground">Captured</p>
              <p class="mt-0.5">{{ formattedDate }}</p>
            </div>

            <div v-if="detail?.caption">
              <p class="text-xs text-muted-foreground">Caption</p>
              <p class="mt-0.5 leading-relaxed">{{ detail.caption }}</p>
            </div>

            <div v-if="detail && detail.labels.length > 0">
              <p class="text-xs text-muted-foreground">Labels</p>
              <div class="mt-1.5 flex flex-wrap gap-1.5">
                <Badge v-for="label in detail.labels" :key="label" variant="secondary">
                  {{ label }}
                </Badge>
              </div>
            </div>

            <div v-if="detail && detail.latitude !== null && detail.longitude !== null">
              <p class="text-xs text-muted-foreground">Location</p>
              <p class="mt-0.5 font-mono text-xs text-muted-foreground">
                {{ detail.latitude.toFixed(5) }}, {{ detail.longitude.toFixed(5) }}
              </p>
            </div>

            <div>
              <p class="text-xs text-muted-foreground">SHA-1 Hash</p>
              <p class="mt-0.5 break-all font-mono text-xs text-muted-foreground">
                {{ item.hash }}
              </p>
            </div>
          </div>
        </aside>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ChevronLeft, ChevronRight, Download, FileText, FolderPlus, Info, X } from 'lucide-vue-next'
import Badge from '../ui/Badge.vue'
import Button from '../ui/Button.vue'
import Skeleton from '../ui/Skeleton.vue'
import type { MediaDetail, MediaGridItem } from '../../types'

const props = defineProps<{
  open: boolean
  item: MediaGridItem | null
  detail: MediaDetail | null
  detailLoading: boolean
  hasPrev: boolean
  hasNext: boolean
  canEditAlbums: boolean
}>()

const emit = defineEmits<{
  close: []
  prev: []
  next: []
  'add-to-album': [hash: string]
}>()

const showInfo = ref(false)

const formattedDate = computed(() => {
  const ts = props.item?.createdAtTimestamp
  if (ts === null || ts === undefined || !Number.isFinite(ts)) {
    return props.item?.createdAt || ''
  }
  const tsMs = Math.abs(ts) < 1e11 ? ts * 1000 : ts
  const date = new Date(tsMs)
  if (Number.isNaN(date.getTime())) {
    return props.item?.createdAt || ''
  }
  return date.toLocaleString()
})

const onKeyDown = (event: KeyboardEvent) => {
  if (!props.open) return
  if (event.key === 'Escape') {
    emit('close')
  } else if (event.key === 'ArrowLeft' && props.hasPrev) {
    emit('prev')
  } else if (event.key === 'ArrowRight' && props.hasNext) {
    emit('next')
  }
}

onMounted(() => {
  if (import.meta.client) {
    window.addEventListener('keydown', onKeyDown)
  }
})

onBeforeUnmount(() => {
  if (import.meta.client) {
    window.removeEventListener('keydown', onKeyDown)
  }
})
</script>

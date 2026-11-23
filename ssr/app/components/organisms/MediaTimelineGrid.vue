<template>
  <div>
    <!-- Initial skeleton grid -->
    <div v-if="loading && items.length === 0" class="ps-masonry-grid" aria-busy="true">
      <Skeleton v-for="n in 12" :key="n" class="ps-masonry-item h-full w-full rounded-sm" />
    </div>

    <!-- Date-grouped masonry sections -->
    <div v-else-if="items.length > 0" class="space-y-6">
      <section v-for="[dateLabel, groupItems] in groupedByDate" :key="dateLabel">
        <div class="mb-2 flex items-center gap-2 px-0.5">
          <Calendar class="h-4 w-4 text-primary" />
          <h2 class="text-sm sm:text-base font-semibold tracking-tight text-foreground">
            {{ dateLabel }}
          </h2>
          <span class="text-xs text-muted-foreground">({{ groupItems.length }})</span>
        </div>

        <div class="ps-masonry-grid">
          <div v-for="item in groupItems" :key="item.hash" class="ps-masonry-item">
            <MediaTile
              :item="item"
              :selected="selectedHashes.has(item.hash)"
              :selecting="selecting"
              :show-select-control="showSelectControl"
              @open="emit('open-item', $event)"
              @toggle-select="emit('toggle-select', $event)"
            />
          </div>
        </div>
      </section>

      <!-- Infinite scroll sentinel + accessible load more fallback -->
      <div ref="sentinelRef" class="flex flex-col items-center justify-center py-4">
        <div v-if="loadingMore" class="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 class="h-4 w-4 animate-spin" />
          <span>Loading more...</span>
        </div>
        <Button v-else-if="hasMore" variant="outline" size="sm" @click="emit('load-more')">
          Load more
        </Button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Calendar, Loader2 } from 'lucide-vue-next'
import MediaTile from '../common/MediaTile.vue'
import Button from '../ui/Button.vue'
import Skeleton from '../ui/Skeleton.vue'
import type { MediaGridItem } from '../../types'

const props = withDefaults(
  defineProps<{
    items: MediaGridItem[]
    loading: boolean
    loadingMore: boolean
    hasMore: boolean
    selecting: boolean
    selectedHashes: Set<string>
    showSelectControl?: boolean
  }>(),
  {
    showSelectControl: true,
  }
)

const emit = defineEmits<{
  'open-item': [item: MediaGridItem]
  'toggle-select': [hash: string]
  'load-more': []
}>()

const sentinelRef = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

const formatDateLabel = (timestamp: number | null): string => {
  if (timestamp === null || !Number.isFinite(timestamp)) {
    return 'Undated'
  }
  const tsMs = Math.abs(timestamp) < 1e11 ? timestamp * 1000 : timestamp
  const date = new Date(tsMs)
  if (Number.isNaN(date.getTime())) {
    return 'Undated'
  }
  return date.toLocaleDateString(undefined, {
    weekday: 'short',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

const groupedByDate = computed(() => {
  const groups = new Map<string, MediaGridItem[]>()
  for (const item of props.items) {
    const label = formatDateLabel(item.createdAtTimestamp)
    const bucket = groups.get(label)
    if (bucket) {
      bucket.push(item)
    } else {
      groups.set(label, [item])
    }
  }
  return groups
})

const setupObserver = () => {
  if (!import.meta.client || typeof IntersectionObserver === 'undefined') return
  observer?.disconnect()
  if (!sentinelRef.value) return
  observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting) && props.hasMore && !props.loadingMore) {
        emit('load-more')
      }
    },
    { rootMargin: '400px 0px' }
  )
  observer.observe(sentinelRef.value)
}

onMounted(() => {
  setupObserver()
})

watch(sentinelRef, () => {
  setupObserver()
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})
</script>

<template>
  <aside
    aria-label="Area media inspector"
    class="pointer-events-auto absolute inset-x-2 bottom-2 z-10 flex max-h-[58%] flex-col overflow-hidden rounded-xl border border-border bg-surface/95 shadow-xl backdrop-blur-md md:inset-x-auto md:inset-y-3 md:right-3 md:max-h-none md:w-96"
  >
    <!-- Header -->
    <div class="flex items-start justify-between gap-2 border-b border-border px-3.5 py-3">
      <div class="min-w-0 space-y-0.5">
        <div class="flex items-center gap-2">
          <h2 class="text-sm font-semibold text-foreground">Area Inspector</h2>
          <Badge variant="secondary">{{ totalCount }} found</Badge>
        </div>
        <p class="truncate text-xs text-muted-foreground">
          {{ centerLat.toFixed(4) }}, {{ centerLng.toFixed(4) }} ·
          {{ formatRadius(radiusKm) }} radius
        </p>
      </div>

      <Button
        variant="ghost"
        size="icon"
        aria-label="Close area inspector"
        class="h-8 w-8 shrink-0"
        @click="emit('close')"
      >
        <X class="h-4 w-4" />
      </Button>
    </div>

    <!-- Body -->
    <div class="min-h-0 flex-1 overflow-y-auto p-3">
      <div v-if="errorMessage" class="mb-3">
        <ErrorBanner :message="errorMessage" retryable @retry="emit('retry')" />
      </div>

      <div v-if="loading && items.length === 0" class="space-y-2.5">
        <div
          v-for="n in 4"
          :key="n"
          class="flex items-center gap-3 rounded-lg border border-border/60 p-2"
        >
          <Skeleton class="h-14 w-14 shrink-0 rounded-md" />
          <div class="flex-1 space-y-2">
            <Skeleton class="h-3.5 w-3/4" />
            <Skeleton class="h-3 w-1/2" />
          </div>
        </div>
      </div>

      <div
        v-else-if="!loading && items.length === 0 && !errorMessage"
        class="flex flex-col items-center justify-center py-8 text-center"
      >
        <MapPinOff class="mb-2 h-8 w-8 text-muted-foreground" />
        <p class="text-sm font-medium text-foreground">No media in this area</p>
        <p class="mt-1 text-xs text-muted-foreground">
          Click another hotspot or zoom out to widen the search radius.
        </p>
      </div>

      <div v-else class="space-y-2">
        <div
          v-for="(item, index) in items"
          :key="item.hash"
          :class="[
            'flex items-center gap-2.5 rounded-lg border p-2 transition-colors',
            pinnedHash === item.hash
              ? 'border-primary bg-primary/8'
              : 'border-border/70 bg-background/60 hover:bg-muted/50',
          ]"
        >
          <button
            type="button"
            class="relative h-14 w-14 shrink-0 overflow-hidden rounded-md bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            :aria-label="`Open ${item.fileName}`"
            @click="emit('open-lightbox', index)"
          >
            <img
              v-if="item.thumbnailUrl"
              :src="item.thumbnailUrl"
              :alt="item.fileName"
              loading="lazy"
              class="h-full w-full object-cover"
            />
            <div
              v-else
              class="flex h-full w-full items-center justify-center text-muted-foreground"
            >
              <Film v-if="item.fileType === 'VIDEO'" class="h-5 w-5" />
              <FileText v-else class="h-5 w-5" />
            </div>
            <span
              v-if="item.fileType === 'VIDEO'"
              class="absolute bottom-1 right-1 rounded bg-black/70 px-1 py-0.5 text-[9px] font-semibold text-white"
            >
              VID
            </span>
          </button>

          <div class="min-w-0 flex-1 space-y-1">
            <button
              type="button"
              class="block w-full truncate text-left text-xs font-medium text-foreground hover:text-primary"
              @click="emit('open-lightbox', index)"
            >
              {{ item.fileName }}
            </button>
            <p class="truncate text-[11px] text-muted-foreground">
              {{ formatDate(item.createdAt) }}
            </p>
            <div class="flex flex-wrap items-center gap-1">
              <Badge
                v-if="item.distanceKm !== undefined && item.distanceKm !== null"
                variant="outline"
                class="text-[10px]"
              >
                {{ formatDistance(item.distanceKm) }}
              </Badge>
              <Badge v-if="item.geohash" variant="secondary" class="font-mono text-[10px]">
                {{ item.geohash.slice(0, 6) }}
              </Badge>
            </div>
          </div>

          <Button
            variant="ghost"
            size="icon"
            :aria-label="`Pin ${item.fileName} on map`"
            :class="
              pinnedHash === item.hash
                ? 'h-8 w-8 shrink-0 text-primary bg-primary/15'
                : 'h-8 w-8 shrink-0 text-muted-foreground'
            "
            :disabled="item.latitude === null || item.longitude === null"
            @click="emit('pin-item', item)"
          >
            <MapPin class="h-4 w-4" />
          </Button>
        </div>

        <div v-if="hasMore" class="pt-2">
          <Button
            variant="outline"
            size="sm"
            class="w-full"
            :disabled="loadingMore"
            @click="emit('load-more')"
          >
            {{ loadingMore ? 'Loading more...' : `Load more (${items.length} / ${totalCount})` }}
          </Button>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { FileText, Film, MapPin, MapPinOff, X } from 'lucide-vue-next'
import ErrorBanner from '../common/ErrorBanner.vue'
import Badge from '../ui/Badge.vue'
import Button from '../ui/Button.vue'
import Skeleton from '../ui/Skeleton.vue'
import type { MediaGridItem } from '../../types'

defineProps<{
  items: MediaGridItem[]
  totalCount: number
  centerLat: number
  centerLng: number
  radiusKm: number
  loading: boolean
  loadingMore: boolean
  hasMore: boolean
  errorMessage: string
  pinnedHash: string | null
}>()

const emit = defineEmits<{
  close: []
  retry: []
  'load-more': []
  'pin-item': [item: MediaGridItem]
  'open-lightbox': [index: number]
}>()

const formatRadius = (km: number): string =>
  km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(km >= 10 ? 0 : 1)} km`

const formatDistance = (km: number): string =>
  km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(2)} km`

const formatDate = (iso: string | null): string => {
  if (!iso) return 'Unknown date'
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return iso
  return parsed.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}
</script>

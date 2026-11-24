<template>
  <div>
    <PageHeader title="World Map" :subtitle="headerSubtitle">
      <template #actions>
        <div class="flex flex-wrap items-center gap-2">
          <Badge v-if="fallbackTriggered" variant="secondary" class="text-xs">
            Auto-clustered (zoom in for raw)
          </Badge>
          <Badge v-else-if="effectiveMode === 'raw'" variant="outline" class="text-xs">
            Raw points
          </Badge>
          <NuxtLink
            to="/settings"
            class="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-foreground no-underline transition-colors hover:bg-muted"
          >
            <SlidersHorizontal class="h-3.5 w-3.5" />
            <span>Map Settings</span>
          </NuxtLink>
        </div>
      </template>
    </PageHeader>

    <SearchFilterBar
      :filters="filters"
      :suggestions="suggestions"
      :location-results="locationResults"
      :location-loading="locationLoading"
      :location-error="locationError"
      @apply-filters="applyFilters"
      @clear-filters="clearAllFilters"
      @query-input="handleSuggestionQuery"
      @location-search="handleLocationSearch"
    />

    <div v-if="heatmapError" class="mb-3">
      <ErrorBanner :message="heatmapError" retryable @retry="triggerHeatmapFetch(true)" />
    </div>

    <div class="relative h-[calc(100dvh-15rem)] min-h-[460px] w-full md:h-[calc(100dvh-12.5rem)]">
      <ClientOnly>
        <div
          ref="mapContainer"
          class="isolate relative z-0 h-full w-full overflow-hidden rounded-xl border border-border bg-muted/40"
        />

        <template #fallback>
          <div
            class="flex h-full w-full items-center justify-center rounded-xl border border-border bg-muted/40"
          >
            <Skeleton class="h-full w-full rounded-xl" />
          </div>
        </template>
      </ClientOnly>

      <div
        v-if="heatmapLoading"
        class="pointer-events-none absolute left-3 top-3 z-10 inline-flex items-center gap-2 rounded-lg border border-border bg-surface/90 px-2.5 py-1 text-xs text-muted-foreground shadow-sm backdrop-blur-sm"
      >
        <span>Updating heatmap...</span>
      </div>

      <MapInspectDrawer
        v-if="inspectOpen"
        :items="inspectItems"
        :total-count="inspectTotalCount"
        :center-lat="inspectLat"
        :center-lng="inspectLng"
        :radius-km="inspectRadiusKm"
        :loading="inspectLoading"
        :loading-more="inspectLoadingMore"
        :has-more="inspectHasMore"
        :error-message="inspectError"
        :pinned-hash="pinnedHash"
        @close="closeInspector"
        @retry="retryInspect"
        @load-more="loadMoreInspect"
        @pin-item="pinItemOnMap"
        @open-lightbox="openLightbox"
      />
    </div>

    <MediaLightbox
      :open="Boolean(activeItem)"
      :item="activeItem"
      :detail="activeDetail"
      :detail-loading="detailLoading"
      :has-prev="hasPrev"
      :has-next="hasNext"
      :can-edit-albums="canEditAlbums"
      @close="closeLightbox"
      @prev="prevItem"
      @next="nextItem"
      @add-to-album="openPicker([$event])"
    />

    <AlbumPickerSheet
      :open="pickerOpen"
      :albums="albums"
      :loading="albumsLoading"
      :submitting="pickerSubmitting"
      :error="pickerError"
      :item-count="targetHashes.length"
      @select-album="addToExistingAlbum($event)"
      @create-and-add="createAlbumWithSelection($event)"
      @close="closePicker"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import type * as LeafletTypes from 'leaflet'
import { SlidersHorizontal } from 'lucide-vue-next'
import ErrorBanner from '../components/common/ErrorBanner.vue'
import AlbumPickerSheet from '../components/organisms/AlbumPickerSheet.vue'
import MapInspectDrawer from '../components/organisms/MapInspectDrawer.vue'
import MediaLightbox from '../components/organisms/MediaLightbox.vue'
import PageHeader from '../components/organisms/PageHeader.vue'
import SearchFilterBar from '../components/organisms/SearchFilterBar.vue'
import Badge from '../components/ui/Badge.vue'
import Skeleton from '../components/ui/Skeleton.vue'
import { useAlbumPicker } from '../composables/useAlbumPicker'
import { useGalleryFilters } from '../composables/useGalleryFilters'
import {
  computeDynamicHeatOptions,
  computeInspectRadiusKm,
  HEATMAP_SETTINGS_UPDATED_EVENT,
  useMapSettings,
} from '../composables/useMapSettings'
import { usePhotosphereApi } from '../composables/usePhotosphereApi'
import { useAuthStore } from '../stores/auth'
import type {
  BasemapStyle,
  HeatmapDataMode,
  LocationSearchResult,
  MediaDetail,
  MediaGridItem,
  SearchFieldMode,
  SearchSuggestion,
} from '../types'

const HEATMAP_GRADIENT: Record<number, string> = {
  0.2: '#2563eb',
  0.45: '#06b6d4',
  0.65: '#22c55e',
  0.85: '#f59e0b',
  1.0: '#ef4444',
}

const ESRI_ATTRIBUTION = 'Tiles &copy; Esri'

const authStore = useAuthStore()
const { canEditAlbums, isAuthenticated } = storeToRefs(authStore)
const { settings, reloadMapSettings } = useMapSettings()
const { filters, applyFilters, clearAllFilters } = useGalleryFilters()
const { fetchHeatmapClusters, listFiles, getFileDetail, fetchSearchSuggestions, searchLocations } =
  usePhotosphereApi()

const mapContainer = ref<HTMLElement | null>(null)

// Search & location autocomplete state
const suggestions = ref<SearchSuggestion[]>([])
const locationResults = ref<LocationSearchResult[]>([])
const locationLoading = ref(false)
const locationError = ref('')

// Heatmap stats & state
const heatmapLoading = ref(false)
const heatmapError = ref('')
const totalGeolocatedCount = ref(0)
const viewportPointCount = ref(0)
const currentPrecision = ref<number>(2)
const effectiveMode = ref<HeatmapDataMode>('geohash')
const fallbackTriggered = ref(false)

// Click-to-inspect state
const inspectOpen = ref(false)
const inspectLat = ref(0)
const inspectLng = ref(0)
const inspectRadiusKm = ref(10)
const inspectItems = ref<MediaGridItem[]>([])
const inspectTotalCount = ref(0)
const inspectPage = ref(1)
const inspectHasMore = ref(false)
const inspectLoading = ref(false)
const inspectLoadingMore = ref(false)
const inspectError = ref('')
const pinnedHash = ref<string | null>(null)

// Lightbox state
const activeIndex = ref<number | null>(null)
const detailCache = ref<Record<string, MediaDetail>>({})
const detailLoading = ref(false)

const activeItem = computed<MediaGridItem | null>(() => {
  if (activeIndex.value === null) return null
  return inspectItems.value[activeIndex.value] ?? null
})

const activeDetail = computed<MediaDetail | null>(() => {
  const item = activeItem.value
  return item ? (detailCache.value[item.hash] ?? null) : null
})

const hasPrev = computed(() => activeIndex.value !== null && activeIndex.value > 0)
const hasNext = computed(
  () => activeIndex.value !== null && activeIndex.value < inspectItems.value.length - 1
)

const headerSubtitle = computed(() => {
  if (totalGeolocatedCount.value === 0) return 'Explore geolocated media across the globe'
  return `${viewportPointCount.value.toLocaleString()} in view · ${totalGeolocatedCount.value.toLocaleString()} geotagged · geohash p${currentPrecision.value}`
})

const {
  pickerOpen,
  targetHashes,
  albums,
  albumsLoading,
  submitting: pickerSubmitting,
  pickerError,
  openPicker,
  closePicker,
  addToExistingAlbum,
  createAlbumWithSelection,
} = useAlbumPicker()

// Leaflet runtime handles (client-only)
let L: typeof LeafletTypes | null = null
let mapInstance: LeafletTypes.Map | null = null
let activeBasemapLayer: LeafletTypes.Layer | null = null
let heatLayer: LeafletTypes.HeatLayer | null = null
let inspectCircle: LeafletTypes.Circle | null = null
let pinMarker: LeafletTypes.CircleMarker | null = null
let moveDebounceTimer: ReturnType<typeof setTimeout> | null = null
let heatmapAbortController: AbortController | null = null
let inspectAbortController: AbortController | null = null

const buildEsriBasemapLayer = (style: BasemapStyle): LeafletTypes.Layer | null => {
  if (!L) return null
  if (style === 'light') {
    return L.layerGroup([
      L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',
        { attribution: ESRI_ATTRIBUTION, maxZoom: 16 }
      ),
      L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}',
        { attribution: ESRI_ATTRIBUTION, maxZoom: 16 }
      ),
    ])
  }
  if (style === 'satellite') {
    return L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      { attribution: ESRI_ATTRIBUTION, maxZoom: 16 }
    )
  }
  return L.layerGroup([
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
      { attribution: ESRI_ATTRIBUTION, maxZoom: 16 }
    ),
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}',
      { attribution: ESRI_ATTRIBUTION, maxZoom: 16 }
    ),
  ])
}

const applyBasemap = (style: BasemapStyle) => {
  if (!mapInstance || !L) return
  if (activeBasemapLayer) {
    mapInstance.removeLayer(activeBasemapLayer)
  }
  const nextLayer = buildEsriBasemapLayer(style)
  if (nextLayer) {
    nextLayer.addTo(mapInstance)
    activeBasemapLayer = nextLayer
  }
}

const applyHeatLayerOptions = () => {
  if (!mapInstance || !heatLayer) return
  const dynamicOpts = computeDynamicHeatOptions(mapInstance.getZoom(), settings.value)
  heatLayer.setOptions({
    radius: dynamicOpts.radius,
    blur: dynamicOpts.blur,
    max: dynamicOpts.max,
  })
}

const fetchHeatmapForCurrentViewport = async () => {
  if (!mapInstance || !heatLayer || !isAuthenticated.value) return
  if (heatmapAbortController) {
    heatmapAbortController.abort()
  }
  heatmapAbortController = new AbortController()
  heatmapLoading.value = true
  heatmapError.value = ''

  try {
    const bounds = mapInstance.getBounds()
    const zoom = mapInstance.getZoom()
    const res = await fetchHeatmapClusters(
      {
        north: bounds.getNorth(),
        south: bounds.getSouth(),
        east: bounds.getEast(),
        west: bounds.getWest(),
        zoom,
        mode: settings.value.dataMode,
      },
      filters.value,
      heatmapAbortController.signal
    )

    totalGeolocatedCount.value = res.totalGeolocatedCount
    viewportPointCount.value = res.viewportPointCount
    currentPrecision.value = res.precision
    effectiveMode.value = res.effectiveMode
    fallbackTriggered.value = res.fallbackTriggered
    heatLayer.setLatLngs(res.points)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return
    }
    heatmapError.value = error instanceof Error ? error.message : 'Failed to load heatmap data'
  } finally {
    heatmapLoading.value = false
  }
}

const triggerHeatmapFetch = (immediate = false) => {
  if (moveDebounceTimer) {
    clearTimeout(moveDebounceTimer)
    moveDebounceTimer = null
  }
  if (immediate) {
    void fetchHeatmapForCurrentViewport()
    return
  }
  moveDebounceTimer = setTimeout(() => {
    void fetchHeatmapForCurrentViewport()
  }, 150)
}

const clearInspectOverlays = () => {
  if (mapInstance && inspectCircle) {
    mapInstance.removeLayer(inspectCircle)
    inspectCircle = null
  }
  if (mapInstance && pinMarker) {
    mapInstance.removeLayer(pinMarker)
    pinMarker = null
  }
  pinnedHash.value = null
}

const fetchInspectPage = async (page: number, append: boolean) => {
  if (inspectAbortController) {
    inspectAbortController.abort()
  }
  inspectAbortController = new AbortController()
  if (append) {
    inspectLoadingMore.value = true
  } else {
    inspectLoading.value = true
  }
  inspectError.value = ''

  try {
    const res = await listFiles(
      {
        ...filters.value,
        lat: inspectLat.value,
        lng: inspectLng.value,
        radiusKm: inspectRadiusKm.value,
      },
      page,
      settings.value.maxInspectResults,
      {
        sort: 'distance',
        signal: inspectAbortController.signal,
      }
    )

    inspectItems.value = append ? [...inspectItems.value, ...res.items] : res.items
    inspectTotalCount.value = res.totalCount
    inspectPage.value = res.page
    inspectHasMore.value = res.hasMore
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return
    }
    inspectError.value = error instanceof Error ? error.message : 'Failed to inspect area'
  } finally {
    inspectLoading.value = false
    inspectLoadingMore.value = false
  }
}

const handleMapClick = (e: LeafletTypes.LeafletMouseEvent) => {
  if (!mapInstance || !L) return
  const zoom = mapInstance.getZoom()
  const radiusKm = computeInspectRadiusKm(zoom)

  inspectLat.value = e.latlng.lat
  inspectLng.value = e.latlng.lng
  inspectRadiusKm.value = radiusKm
  inspectOpen.value = true
  inspectItems.value = []
  inspectTotalCount.value = 0
  inspectPage.value = 1
  inspectHasMore.value = false
  pinnedHash.value = null

  if (inspectCircle) {
    mapInstance.removeLayer(inspectCircle)
  }
  if (pinMarker) {
    mapInstance.removeLayer(pinMarker)
    pinMarker = null
  }

  inspectCircle = L.circle([e.latlng.lat, e.latlng.lng], {
    radius: radiusKm * 1000,
    color: '#3b82f6',
    fillColor: '#3b82f6',
    fillOpacity: 0.12,
    weight: 2,
    dashArray: '6, 6',
  }).addTo(mapInstance)

  void fetchInspectPage(1, false)
}

const closeInspector = () => {
  inspectOpen.value = false
  clearInspectOverlays()
}

const retryInspect = () => {
  void fetchInspectPage(1, false)
}

const loadMoreInspect = () => {
  if (!inspectHasMore.value || inspectLoadingMore.value) return
  void fetchInspectPage(inspectPage.value + 1, true)
}

const pinItemOnMap = (item: MediaGridItem) => {
  if (!mapInstance || !L || item.latitude === null || item.longitude === null) return
  pinnedHash.value = item.hash

  if (pinMarker) {
    mapInstance.removeLayer(pinMarker)
  }

  pinMarker = L.circleMarker([item.latitude, item.longitude], {
    radius: 8,
    color: '#ef4444',
    fillColor: '#f97316',
    fillOpacity: 0.9,
    weight: 2,
  })
    .bindTooltip(
      `${item.fileName}${item.distanceKm !== undefined && item.distanceKm !== null ? ` (${item.distanceKm.toFixed(2)} km)` : ''}`,
      { direction: 'top', offset: [0, -8] }
    )
    .addTo(mapInstance)

  pinMarker.openTooltip()
  mapInstance.panTo([item.latitude, item.longitude], { animate: true })
}

// Lightbox navigation & detail loading
const loadDetailIfNeeded = async (hash: string) => {
  if (detailCache.value[hash]) return
  detailLoading.value = true
  try {
    const detail = await getFileDetail(hash)
    detailCache.value = { ...detailCache.value, [hash]: detail }
  } catch {
    // Keep lightbox usable with grid item metadata
  } finally {
    detailLoading.value = false
  }
}

const openLightbox = (index: number) => {
  activeIndex.value = index
  const item = inspectItems.value[index]
  if (item) {
    void loadDetailIfNeeded(item.hash)
  }
}

const closeLightbox = () => {
  activeIndex.value = null
}

const prevItem = () => {
  if (!hasPrev.value || activeIndex.value === null) return
  openLightbox(activeIndex.value - 1)
}

const nextItem = () => {
  if (!hasNext.value || activeIndex.value === null) return
  openLightbox(activeIndex.value + 1)
}

const handleSuggestionQuery = async ({ q, field }: { q: string; field: SearchFieldMode }) => {
  if (!q.trim()) {
    suggestions.value = []
    return
  }
  try {
    suggestions.value = await fetchSearchSuggestions(q, field, 10)
  } catch {
    suggestions.value = []
  }
}

const handleLocationSearch = async (q: string) => {
  locationLoading.value = true
  locationError.value = ''
  try {
    locationResults.value = await searchLocations(q)
  } catch (error) {
    locationResults.value = []
    locationError.value =
      error instanceof Error ? error.message : 'Failed to search location via OpenStreetMap'
  } finally {
    locationLoading.value = false
  }
}

const handleExternalSettingsEvent = () => {
  reloadMapSettings()
}

let mapInitializing = false

const initializeMap = async (containerEl: HTMLElement) => {
  if (!import.meta.client || mapInstance || mapInitializing) return
  mapInitializing = true
  try {
    reloadMapSettings()

    const leafletModule = await import('leaflet')
    L = (leafletModule.default ?? leafletModule) as typeof LeafletTypes
    ;(window as unknown as { L: typeof LeafletTypes }).L = L
    await import('leaflet/dist/leaflet.css')
    await import('leaflet.heat')

    if (!mapContainer.value || mapInstance) return

    const initialLat = filters.value.lat ?? 25
    const initialLng = filters.value.lng ?? 10
    const initialZoom = filters.value.lat !== undefined && filters.value.lng !== undefined ? 10 : 3

    mapInstance = L.map(containerEl, {
      preferCanvas: true,
      minZoom: 2,
      maxZoom: 16,
      worldCopyJump: true,
      center: [initialLat, initialLng],
      zoom: initialZoom,
    })

    applyBasemap(settings.value.basemap)

    const initialHeatOpts = computeDynamicHeatOptions(initialZoom, settings.value)
    heatLayer = L.heatLayer([], {
      radius: initialHeatOpts.radius,
      blur: initialHeatOpts.blur,
      max: initialHeatOpts.max,
      minOpacity: 0.35,
      gradient: HEATMAP_GRADIENT,
    }).addTo(mapInstance)

    mapInstance.on('zoomend', () => {
      applyHeatLayerOptions()
      triggerHeatmapFetch(false)
    })
    mapInstance.on('moveend', () => {
      triggerHeatmapFetch(false)
    })
    mapInstance.on('click', handleMapClick)

    window.addEventListener(HEATMAP_SETTINGS_UPDATED_EVENT, handleExternalSettingsEvent)
    triggerHeatmapFetch(true)
  } catch (error) {
    heatmapError.value = error instanceof Error ? error.message : 'Failed to initialize map'
  } finally {
    mapInitializing = false
  }
}

watch(
  mapContainer,
  (el) => {
    if (el) {
      void initializeMap(el)
    }
  },
  { flush: 'post', immediate: true }
)

watch(isAuthenticated, (authed) => {
  if (authed && mapInstance && heatLayer) {
    triggerHeatmapFetch(true)
  }
})

watch(
  () => settings.value.basemap,
  (nextBasemap) => {
    applyBasemap(nextBasemap)
  }
)

watch(
  () => [
    settings.value.dynamicRadius,
    settings.value.baseRadius,
    settings.value.blur,
    settings.value.maxIntensity,
  ],
  () => {
    applyHeatLayerOptions()
  }
)

watch(
  () => settings.value.dataMode,
  () => {
    triggerHeatmapFetch(true)
  }
)

watch(
  () => filters.value,
  (nextFilters, prevFilters) => {
    if (
      mapInstance &&
      nextFilters.lat !== undefined &&
      nextFilters.lng !== undefined &&
      (nextFilters.lat !== prevFilters?.lat || nextFilters.lng !== prevFilters?.lng)
    ) {
      mapInstance.flyTo([nextFilters.lat, nextFilters.lng], Math.max(mapInstance.getZoom(), 10))
    }
    triggerHeatmapFetch(true)
    if (inspectOpen.value) {
      void fetchInspectPage(1, false)
    }
  },
  { deep: true }
)

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener(HEATMAP_SETTINGS_UPDATED_EVENT, handleExternalSettingsEvent)
  }
  if (moveDebounceTimer) {
    clearTimeout(moveDebounceTimer)
  }
  if (heatmapAbortController) {
    heatmapAbortController.abort()
  }
  if (inspectAbortController) {
    inspectAbortController.abort()
  }
  if (mapInstance) {
    mapInstance.remove()
    mapInstance = null
  }
  heatLayer = null
  activeBasemapLayer = null
  inspectCircle = null
  pinMarker = null
})
</script>

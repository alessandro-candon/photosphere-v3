<template>
  <div class="mb-4 space-y-2.5">
    <div class="flex flex-wrap items-center gap-2">
      <!-- Scope Selector (Tags vs Captions) -->
      <Select
        id="search-field-select"
        :model-value="selectedField"
        aria-label="Search scope"
        class="w-32 sm:w-36 shrink-0"
        @update:model-value="onFieldChange"
      >
        <option value="labels">Tags</option>
        <option value="captions">Captions</option>
      </Select>

      <!-- Search box + autocomplete suggestions -->
      <div class="relative min-w-[200px] flex-1">
        <Search
          class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          :model-value="searchText"
          type="search"
          :placeholder="selectedField === 'captions' ? 'Search captions...' : 'Search tags...'"
          :aria-label="selectedField === 'captions' ? 'Search captions' : 'Search tags'"
          class="pl-9 pr-9"
          @update:model-value="onSearchInput"
          @keydown.enter.prevent="submitSearch"
          @focus="suggestionsOpen = true"
        />
        <button
          v-if="searchText"
          type="button"
          aria-label="Clear search query"
          class="absolute right-1 top-1/2 flex min-h-9 min-w-9 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
          @click="clearQuery"
        >
          <X class="h-4 w-4" />
        </button>

        <!-- Suggestions dropdown -->
        <div
          v-if="suggestionsOpen && suggestions.length > 0 && searchText.trim()"
          class="absolute left-0 right-0 top-full z-20 mt-1 max-h-64 overflow-y-auto rounded-xl border border-border bg-surface-elevated p-1 shadow-lg"
          role="listbox"
        >
          <button
            v-for="item in suggestions"
            :key="`${item.kind}-${item.index}`"
            type="button"
            class="flex min-h-11 w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-muted"
            @click="pickSuggestion(item)"
          >
            <span class="truncate text-foreground">{{ item.text }}</span>
            <Badge variant="outline">{{ item.kind === 'label' ? 'tag' : 'caption' }}</Badge>
          </button>
        </div>
      </div>

      <Button variant="default" @click="submitSearch">Search</Button>

      <Button variant="outline" @click="openFilterSheet">
        <SlidersHorizontal class="h-4 w-4" />
        <span>Filters</span>
        <Badge v-if="activeFilterCount > 0" variant="default" class="ml-0.5">
          {{ activeFilterCount }}
        </Badge>
      </Button>
    </div>

    <!-- Active filter chips -->
    <div v-if="hasAnyActiveFilter" class="flex flex-wrap items-center gap-1.5">
      <Badge
        v-if="filters.q || filters.labelIndex !== undefined || filters.captionIndex !== undefined"
        variant="secondary"
        class="gap-1.5 py-1 pl-2.5 pr-1.5"
      >
        <span>
          {{ activeScopeLabel }}: "{{
            filters.q ||
            (filters.labelIndex !== undefined
              ? `#${filters.labelIndex}`
              : `#${filters.captionIndex}`)
          }}"
        </span>
        <button
          type="button"
          aria-label="Remove search query filter"
          class="rounded-full p-0.5 hover:bg-background/60"
          @click="removeFilter('q')"
        >
          <X class="h-3 w-3" />
        </button>
      </Badge>

      <Badge v-if="filters.fileType" variant="secondary" class="gap-1.5 py-1 pl-2.5 pr-1.5">
        <span>Type: {{ filters.fileType }}</span>
        <button
          type="button"
          aria-label="Remove media type filter"
          class="rounded-full p-0.5 hover:bg-background/60"
          @click="removeFilter('fileType')"
        >
          <X class="h-3 w-3" />
        </button>
      </Badge>

      <Badge
        v-if="filters.dateFrom || filters.dateTo"
        variant="secondary"
        class="gap-1.5 py-1 pl-2.5 pr-1.5"
      >
        <span>Dates: {{ filters.dateFrom || '...' }} to {{ filters.dateTo || '...' }}</span>
        <button
          type="button"
          aria-label="Remove date range filter"
          class="rounded-full p-0.5 hover:bg-background/60"
          @click="removeFilter('dates')"
        >
          <X class="h-3 w-3" />
        </button>
      </Badge>

      <Badge
        v-if="filters.lat !== undefined && filters.lng !== undefined"
        variant="secondary"
        class="gap-1.5 py-1 pl-2.5 pr-1.5"
      >
        <MapPin class="h-3 w-3" />
        <span>
          {{ filters.place || `${filters.lat.toFixed(2)}, ${filters.lng.toFixed(2)}` }}
          ({{ filters.radiusKm ?? 10 }} km)
        </span>
        <button
          type="button"
          aria-label="Remove location filter"
          class="rounded-full p-0.5 hover:bg-background/60"
          @click="removeFilter('location')"
        >
          <X class="h-3 w-3" />
        </button>
      </Badge>

      <Badge v-if="filters.notInAlbum" variant="secondary" class="gap-1.5 py-1 pl-2.5 pr-1.5">
        <span>Not in any album</span>
        <button
          type="button"
          aria-label="Remove not-in-album filter"
          class="rounded-full p-0.5 hover:bg-background/60"
          @click="removeFilter('notInAlbum')"
        >
          <X class="h-3 w-3" />
        </button>
      </Badge>

      <Button variant="ghost" size="sm" @click="emit('clear-filters')">Clear all</Button>
    </div>

    <!-- Filter Sheet -->
    <Sheet
      :open="sheetOpen"
      title="Filter Media"
      description="Filter by media type, date range, album membership, or OpenStreetMap place."
      @close="sheetOpen = false"
    >
      <div class="space-y-5">
        <div class="space-y-1.5">
          <label for="filter-file-type" class="text-xs font-medium text-muted-foreground">
            Media Type
          </label>
          <Select id="filter-file-type" v-model="draftFileType">
            <option value="">All types</option>
            <option value="IMAGE">Images</option>
            <option value="VIDEO">Videos</option>
            <option value="FILE">Files</option>
          </Select>
        </div>

        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div class="space-y-1.5">
            <label for="filter-date-from" class="text-xs font-medium text-muted-foreground">
              From date
            </label>
            <Input id="filter-date-from" v-model="draftDateFrom" type="date" />
          </div>
          <div class="space-y-1.5">
            <label for="filter-date-to" class="text-xs font-medium text-muted-foreground">
              To date
            </label>
            <Input id="filter-date-to" v-model="draftDateTo" type="date" />
          </div>
        </div>

        <label class="flex min-h-11 cursor-pointer items-center gap-2.5 text-sm">
          <input
            v-model="draftNotInAlbum"
            type="checkbox"
            class="h-4 w-4 rounded border-border accent-primary"
          />
          <span>Only show items not in any album</span>
        </label>

        <!-- OSM Location Search -->
        <div class="space-y-2.5 rounded-xl border border-border bg-surface p-3">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Location (OpenStreetMap)
            </span>
            <Button
              v-if="draftLat !== undefined"
              variant="ghost"
              size="sm"
              @click="clearDraftLocation"
            >
              Clear place
            </Button>
          </div>

          <div class="flex gap-2">
            <Input
              v-model="placeInput"
              placeholder="Search city or landmark..."
              aria-label="Search place with OpenStreetMap"
              @keydown.enter.prevent="triggerLocationSearch"
            />
            <Button
              variant="secondary"
              :disabled="locationLoading || placeInput.trim().length < 2"
              @click="triggerLocationSearch"
            >
              {{ locationLoading ? 'Searching...' : 'Find' }}
            </Button>
          </div>

          <ErrorBanner v-if="locationError" :message="locationError" />

          <div v-if="locationResults.length > 0" class="max-h-40 space-y-1 overflow-y-auto">
            <button
              v-for="loc in locationResults"
              :key="loc.placeId"
              type="button"
              class="flex min-h-11 w-full items-start gap-2 rounded-lg border border-border bg-background px-3 py-2 text-left text-xs hover:bg-muted"
              @click="selectLocationResult(loc)"
            >
              <MapPin class="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
              <span class="text-foreground">{{ loc.displayName }}</span>
            </button>
          </div>

          <div v-if="draftLat !== undefined && draftLng !== undefined" class="space-y-2">
            <p class="text-xs text-foreground">
              Selected:
              <strong>{{ draftPlace || `${draftLat.toFixed(3)}, ${draftLng.toFixed(3)}` }}</strong>
            </p>
            <div class="space-y-1">
              <label for="filter-radius" class="text-xs text-muted-foreground">Radius</label>
              <Select id="filter-radius" v-model="draftRadiusStr">
                <option value="1">1 km</option>
                <option value="5">5 km</option>
                <option value="10">10 km</option>
                <option value="25">25 km</option>
                <option value="50">50 km</option>
                <option value="100">100 km</option>
              </Select>
            </div>
          </div>
        </div>

        <div class="flex flex-wrap justify-end gap-2 border-t border-border pt-3">
          <Button variant="outline" @click="sheetOpen = false">Cancel</Button>
          <Button @click="applyDraftFilters">Apply Filters</Button>
        </div>
      </div>
    </Sheet>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { MapPin, Search, SlidersHorizontal, X } from 'lucide-vue-next'
import ErrorBanner from '../common/ErrorBanner.vue'
import Badge from '../ui/Badge.vue'
import Button from '../ui/Button.vue'
import Input from '../ui/Input.vue'
import Select from '../ui/Select.vue'
import Sheet from '../ui/Sheet.vue'
import type {
  GalleryFilters,
  LocationSearchResult,
  MediaFileType,
  SearchFieldMode,
  SearchSuggestion,
} from '../../types'

const props = defineProps<{
  filters: GalleryFilters
  suggestions: SearchSuggestion[]
  locationResults: LocationSearchResult[]
  locationLoading: boolean
  locationError: string
}>()

const emit = defineEmits<{
  'apply-filters': [filters: GalleryFilters]
  'clear-filters': []
  'query-input': [payload: { q: string; field: SearchFieldMode }]
  'location-search': [q: string]
}>()

const selectedField = ref<SearchFieldMode>(props.filters.searchField || 'labels')
const searchText = ref(props.filters.q || '')
const suggestionsOpen = ref(false)
const sheetOpen = ref(false)

const draftFileType = ref<string>(props.filters.fileType || '')
const draftDateFrom = ref(props.filters.dateFrom || '')
const draftDateTo = ref(props.filters.dateTo || '')
const draftNotInAlbum = ref(Boolean(props.filters.notInAlbum))
const placeInput = ref(props.filters.place || '')
const draftLat = ref<number | undefined>(props.filters.lat)
const draftLng = ref<number | undefined>(props.filters.lng)
const draftPlace = ref<string | undefined>(props.filters.place)
const draftRadiusStr = ref(String(props.filters.radiusKm ?? 10))

let suggestTimer: ReturnType<typeof setTimeout> | null = null

watch(
  () => props.filters,
  (next) => {
    if (next.searchField) {
      selectedField.value = next.searchField
    } else if (next.captionIndex !== undefined) {
      selectedField.value = 'captions'
    } else if (next.labelIndex !== undefined) {
      selectedField.value = 'labels'
    }
    searchText.value = next.q || ''
    draftFileType.value = next.fileType || ''
    draftDateFrom.value = next.dateFrom || ''
    draftDateTo.value = next.dateTo || ''
    draftNotInAlbum.value = Boolean(next.notInAlbum)
    draftLat.value = next.lat
    draftLng.value = next.lng
    draftPlace.value = next.place
    placeInput.value = next.place || ''
    draftRadiusStr.value = String(next.radiusKm ?? 10)
  },
  { deep: true }
)

const activeScopeLabel = computed(() =>
  props.filters.searchField === 'captions' || props.filters.captionIndex !== undefined
    ? 'Captions'
    : 'Tags'
)

const activeFilterCount = computed(() => {
  let count = 0
  if (props.filters.fileType) count += 1
  if (props.filters.dateFrom || props.filters.dateTo) count += 1
  if (props.filters.lat !== undefined && props.filters.lng !== undefined) count += 1
  if (props.filters.notInAlbum) count += 1
  return count
})

const hasAnyActiveFilter = computed(
  () =>
    Boolean(props.filters.q) ||
    props.filters.labelIndex !== undefined ||
    props.filters.captionIndex !== undefined ||
    activeFilterCount.value > 0
)

const onFieldChange = (rawField: string) => {
  const nextField: SearchFieldMode = rawField === 'captions' ? 'captions' : 'labels'
  selectedField.value = nextField
  searchText.value = ''
  suggestionsOpen.value = false
  if (suggestTimer) clearTimeout(suggestTimer)
  emit('query-input', { q: '', field: nextField })

  if (
    props.filters.q ||
    props.filters.labelIndex !== undefined ||
    props.filters.captionIndex !== undefined ||
    props.filters.searchField
  ) {
    emit('apply-filters', {
      ...props.filters,
      searchField: nextField,
      q: undefined,
      labelIndex: undefined,
      captionIndex: undefined,
    })
  }
}

const onSearchInput = (value: string) => {
  searchText.value = value
  suggestionsOpen.value = true
  if (suggestTimer) clearTimeout(suggestTimer)
  suggestTimer = setTimeout(() => {
    emit('query-input', { q: value, field: selectedField.value })
  }, 250)
}

const submitSearch = () => {
  suggestionsOpen.value = false
  const trimmed = searchText.value.trim()
  emit('apply-filters', {
    ...props.filters,
    searchField: trimmed ? selectedField.value : props.filters.searchField,
    q: trimmed || undefined,
    labelIndex: undefined,
    captionIndex: undefined,
  })
}

const pickSuggestion = (item: SearchSuggestion) => {
  const itemField: SearchFieldMode = item.kind === 'caption' ? 'captions' : 'labels'
  selectedField.value = itemField
  searchText.value = item.text
  suggestionsOpen.value = false
  emit('apply-filters', {
    ...props.filters,
    searchField: itemField,
    q: item.text,
    labelIndex: itemField === 'labels' ? item.index : undefined,
    captionIndex: itemField === 'captions' ? item.index : undefined,
  })
}

const clearQuery = () => {
  searchText.value = ''
  suggestionsOpen.value = false
  emit('query-input', { q: '', field: selectedField.value })
  emit('apply-filters', {
    ...props.filters,
    q: undefined,
    labelIndex: undefined,
    captionIndex: undefined,
  })
}

const openFilterSheet = () => {
  suggestionsOpen.value = false
  sheetOpen.value = true
}

const triggerLocationSearch = () => {
  if (placeInput.value.trim().length >= 2) {
    emit('location-search', placeInput.value.trim())
  }
}

const selectLocationResult = (loc: LocationSearchResult) => {
  draftLat.value = loc.lat
  draftLng.value = loc.lng
  draftPlace.value = loc.displayName
  placeInput.value = loc.displayName
}

const clearDraftLocation = () => {
  draftLat.value = undefined
  draftLng.value = undefined
  draftPlace.value = undefined
  placeInput.value = ''
}

const applyDraftFilters = () => {
  sheetOpen.value = false
  const trimmed = searchText.value.trim()
  emit('apply-filters', {
    q: trimmed || undefined,
    searchField: trimmed || props.filters.searchField ? selectedField.value : undefined,
    labelIndex: trimmed === props.filters.q ? props.filters.labelIndex : undefined,
    captionIndex: trimmed === props.filters.q ? props.filters.captionIndex : undefined,
    fileType: (draftFileType.value || undefined) as MediaFileType | undefined,
    dateFrom: draftDateFrom.value || undefined,
    dateTo: draftDateTo.value || undefined,
    notInAlbum: draftNotInAlbum.value || undefined,
    lat: draftLat.value,
    lng: draftLng.value,
    place: draftPlace.value,
    radiusKm:
      draftLat.value !== undefined && draftLng.value !== undefined
        ? Number(draftRadiusStr.value) || 10
        : undefined,
  })
}

const removeFilter = (key: 'q' | 'fileType' | 'dates' | 'location' | 'notInAlbum') => {
  const next: GalleryFilters = { ...props.filters }
  if (key === 'q') {
    next.q = undefined
    next.labelIndex = undefined
    next.captionIndex = undefined
  }
  if (key === 'fileType') next.fileType = undefined
  if (key === 'dates') {
    next.dateFrom = undefined
    next.dateTo = undefined
  }
  if (key === 'location') {
    next.lat = undefined
    next.lng = undefined
    next.radiusKm = undefined
    next.place = undefined
  }
  if (key === 'notInAlbum') next.notInAlbum = undefined
  emit('apply-filters', next)
}
</script>

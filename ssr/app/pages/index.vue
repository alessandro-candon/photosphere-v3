<template>
  <div>
    <PageHeader title="Photos" :subtitle="totalCount > 0 ? `${totalCount} items` : undefined">
      <template #actions>
        <Button
          v-if="items.length > 0 && canEditAlbums"
          :variant="selecting ? 'default' : 'outline'"
          size="sm"
          @click="selectionStore.toggleSelecting"
        >
          {{ selecting ? 'Done selecting' : 'Select' }}
        </Button>
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

    <div v-if="errorMessage" class="mb-4">
      <ErrorBanner
        :message="errorMessage"
        :request-id="errorRequestId"
        retryable
        @retry="loadInitial"
      />
    </div>

    <MediaTimelineGrid
      :items="items"
      :loading="loading"
      :loading-more="loadingMore"
      :has-more="hasMore"
      :selecting="selecting"
      :selected-hashes="selectedHashes"
      :show-select-control="canEditAlbums"
      @open-item="openLightbox"
      @toggle-select="selectionStore.toggleHash"
      @load-more="loadMore"
    />

    <EmptyState
      v-if="!loading && items.length === 0 && !errorMessage"
      icon="search"
      title="No matching photos or videos"
      description="Try clearing or adjusting your active search and filter criteria."
    />

    <SelectionActionBar
      v-if="canEditAlbums"
      :selected-count="selectedCount"
      mode="gallery"
      @add-to-album="openPicker(selectedList)"
      @clear="selectionStore.clearSelection"
    />

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
      @select-album="addToExistingAlbum($event, onAlbumAssigned)"
      @create-and-add="createAlbumWithSelection($event, onAlbumAssigned)"
      @close="closePicker"
    />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount } from 'vue'
import { storeToRefs } from 'pinia'
import EmptyState from '../components/common/EmptyState.vue'
import ErrorBanner from '../components/common/ErrorBanner.vue'
import AlbumPickerSheet from '../components/organisms/AlbumPickerSheet.vue'
import MediaLightbox from '../components/organisms/MediaLightbox.vue'
import MediaTimelineGrid from '../components/organisms/MediaTimelineGrid.vue'
import PageHeader from '../components/organisms/PageHeader.vue'
import SearchFilterBar from '../components/organisms/SearchFilterBar.vue'
import SelectionActionBar from '../components/organisms/SelectionActionBar.vue'
import Button from '../components/ui/Button.vue'
import { useAlbumPicker } from '../composables/useAlbumPicker'
import { useGalleryFilters } from '../composables/useGalleryFilters'
import { useMediaFeed } from '../composables/useMediaFeed'
import { useSearchAutocomplete } from '../composables/useSearchAutocomplete'
import { useAuthStore } from '../stores/auth'
import { useSelectionStore } from '../stores/selection'

const authStore = useAuthStore()
const selectionStore = useSelectionStore()
const { canEditAlbums } = storeToRefs(authStore)
const { selecting, selectedHashes, selectedCount, selectedList } = storeToRefs(selectionStore)
const { filters, applyFilters, clearAllFilters } = useGalleryFilters()
const {
  suggestions,
  locationResults,
  locationLoading,
  locationError,
  handleSuggestionQuery,
  handleLocationSearch,
} = useSearchAutocomplete()

const {
  items,
  totalCount,
  hasMore,
  loading,
  loadingMore,
  errorMessage,
  errorRequestId,
  activeItem,
  activeDetail,
  detailLoading,
  hasPrev,
  hasNext,
  loadInitial,
  loadMore,
  openLightbox,
  closeLightbox,
  prevItem,
  nextItem,
} = useMediaFeed(() => filters.value)

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

const onAlbumAssigned = () => {
  if (selecting.value) {
    selectionStore.clearSelection()
  }
}

onBeforeUnmount(() => {
  selectionStore.clearSelection()
})
</script>

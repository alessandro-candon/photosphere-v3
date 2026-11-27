<template>
  <div>
    <PageHeader title="Memories" :subtitle="`On This Day · ${formattedDateLabel}`" />

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
      :selecting="false"
      :selected-hashes="emptySelection"
      :show-select-control="false"
      @open-item="openLightbox"
      @load-more="loadMore"
    />

    <EmptyState
      v-if="!loading && items.length === 0 && !errorMessage"
      icon="heart"
      title="No memories for this day"
      :description="`No photos or videos were captured on ${formattedDateLabel} in previous years.`"
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
      @select-album="addToExistingAlbum($event)"
      @create-and-add="createAlbumWithSelection($event)"
      @close="closePicker"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute } from '#imports'
import { MONTH_DAY_REGEX } from '#shared/constants'
import EmptyState from '../components/common/EmptyState.vue'
import ErrorBanner from '../components/common/ErrorBanner.vue'
import AlbumPickerSheet from '../components/organisms/AlbumPickerSheet.vue'
import MediaLightbox from '../components/organisms/MediaLightbox.vue'
import MediaTimelineGrid from '../components/organisms/MediaTimelineGrid.vue'
import PageHeader from '../components/organisms/PageHeader.vue'
import { useAlbumPicker } from '../composables/useAlbumPicker'
import { useMediaFeed } from '../composables/useMediaFeed'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const authStore = useAuthStore()
const { canEditAlbums } = storeToRefs(authStore)

const emptySelection = new Set<string>()

const activeMonthDay = computed(() => {
  const queryDate = typeof route.query.date === 'string' ? route.query.date.trim() : ''
  if (MONTH_DAY_REGEX.test(queryDate)) {
    return queryDate
  }
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${month}-${day}`
})

const formattedDateLabel = computed(() => {
  const [rawM, rawD] = activeMonthDay.value.split('-')
  const date = new Date(Date.UTC(2024, Number(rawM) - 1, Number(rawD)))
  if (Number.isNaN(date.getTime())) {
    return activeMonthDay.value
  }
  return date.toLocaleDateString(undefined, {
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',
  })
})

const {
  items,
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
} = useMediaFeed(() => ({ memoryDate: activeMonthDay.value }))

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
</script>

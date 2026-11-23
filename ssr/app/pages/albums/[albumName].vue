<template>
  <div>
    <PageHeader
      :title="albumName"
      :subtitle="totalCount > 0 ? `${totalCount} items` : undefined"
      back-to="/albums"
    >
      <template #actions>
        <Button
          v-if="items.length > 0 && canEditAlbums"
          :variant="selecting ? 'default' : 'outline'"
          size="sm"
          @click="selectionStore.toggleSelecting"
        >
          {{ selecting ? 'Done' : 'Select' }}
        </Button>

        <Button
          v-if="canEditAlbums"
          variant="outline"
          size="sm"
          aria-label="Rename album"
          @click="openRename"
        >
          <Pencil class="h-4 w-4" />
          <span class="hidden sm:inline">Rename</span>
        </Button>

        <Button
          v-if="canEditAlbums"
          variant="outline"
          size="sm"
          class="text-destructive hover:text-destructive"
          aria-label="Delete album"
          @click="deleteOpen = true"
        >
          <Trash2 class="h-4 w-4" />
          <span class="hidden sm:inline">Delete</span>
        </Button>
      </template>
    </PageHeader>

    <div v-if="bannerError" class="mb-4">
      <ErrorBanner
        :message="bannerError"
        :request-id="errorRequestId"
        retryable
        @retry="reloadAll"
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
      v-if="!loading && items.length === 0 && !bannerError"
      icon="folder"
      title="This album is empty"
      description="Select photos in your Photos timeline and add them to this album."
    />

    <SelectionActionBar
      v-if="canEditAlbums"
      :selected-count="selectedCount"
      mode="album"
      :submitting="mutating"
      @remove-from-album="handleRemoveSelected"
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
      @select-album="addToExistingAlbum($event)"
      @create-and-add="createAlbumWithSelection($event)"
      @close="closePicker"
    />

    <AlbumEditorDialog
      :open="renameOpen"
      mode="rename"
      :initial-name="albumName"
      :submitting="renameSubmitting"
      :error="renameError"
      @submit="submitRename"
      @close="renameOpen = false"
    />

    <ConfirmDialog
      :open="deleteOpen"
      title="Delete Album"
      :description="`Delete album '${albumName}'? Photos and videos in your archive will not be deleted.`"
      confirm-label="Delete"
      destructive
      :submitting="deleteSubmitting"
      @confirm="confirmDelete"
      @cancel="deleteOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { navigateTo, useRoute } from '#imports'
import { Pencil, Trash2 } from 'lucide-vue-next'
import ConfirmDialog from '../../components/common/ConfirmDialog.vue'
import EmptyState from '../../components/common/EmptyState.vue'
import ErrorBanner from '../../components/common/ErrorBanner.vue'
import AlbumEditorDialog from '../../components/organisms/AlbumEditorDialog.vue'
import AlbumPickerSheet from '../../components/organisms/AlbumPickerSheet.vue'
import MediaLightbox from '../../components/organisms/MediaLightbox.vue'
import MediaTimelineGrid from '../../components/organisms/MediaTimelineGrid.vue'
import PageHeader from '../../components/organisms/PageHeader.vue'
import SelectionActionBar from '../../components/organisms/SelectionActionBar.vue'
import Button from '../../components/ui/Button.vue'
import { useAlbumPicker } from '../../composables/useAlbumPicker'
import { useMediaFeed } from '../../composables/useMediaFeed'
import { usePhotosphereApi } from '../../composables/usePhotosphereApi'
import { useAuthStore } from '../../stores/auth'
import { useSelectionStore } from '../../stores/selection'

const route = useRoute()
const authStore = useAuthStore()
const selectionStore = useSelectionStore()
const { canEditAlbums } = storeToRefs(authStore)
const { selecting, selectedHashes, selectedCount, selectedList } = storeToRefs(selectionStore)
const { updateAlbum, deleteAlbum } = usePhotosphereApi()

const albumName = computed(() => {
  const raw = String(route.params.albumName || '')
  try {
    return decodeURIComponent(raw)
  } catch {
    return raw
  }
})

const actionError = ref('')
const mutating = ref(false)
const renameOpen = ref(false)
const renameSubmitting = ref(false)
const renameError = ref('')
const deleteOpen = ref(false)
const deleteSubmitting = ref(false)

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
} = useMediaFeed(() => ({ album: albumName.value }))

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

const bannerError = computed(() => actionError.value || errorMessage.value)

const reloadAll = async () => {
  actionError.value = ''
  await loadInitial()
}

const handleRemoveSelected = async () => {
  if (selectedList.value.length === 0) return
  mutating.value = true
  actionError.value = ''
  try {
    await updateAlbum(albumName.value, { removeHashes: selectedList.value })
    selectionStore.clearSelection()
    await loadInitial()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : 'Failed to remove items from album'
  } finally {
    mutating.value = false
  }
}

const openRename = () => {
  renameError.value = ''
  renameOpen.value = true
}

const submitRename = async (newName: string) => {
  renameSubmitting.value = true
  renameError.value = ''
  try {
    const res = await updateAlbum(albumName.value, { newName })
    renameOpen.value = false
    await navigateTo(`/albums/${encodeURIComponent(res.album.name)}`)
  } catch (error) {
    renameError.value = error instanceof Error ? error.message : 'Failed to rename album'
  } finally {
    renameSubmitting.value = false
  }
}

const confirmDelete = async () => {
  deleteSubmitting.value = true
  try {
    await deleteAlbum(albumName.value)
    deleteOpen.value = false
    await navigateTo('/albums')
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : 'Failed to delete album'
    deleteOpen.value = false
  } finally {
    deleteSubmitting.value = false
  }
}

onBeforeUnmount(() => {
  selectionStore.clearSelection()
})
</script>

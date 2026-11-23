<template>
  <div>
    <PageHeader title="Albums" :subtitle="totalCount > 0 ? `${totalCount} albums` : undefined">
      <template #actions>
        <Button v-if="canEditAlbums" size="sm" @click="openCreateDialog">
          <Plus class="h-4 w-4" />
          <span>New Album</span>
        </Button>
      </template>
    </PageHeader>

    <div v-if="errorMessage" class="mb-4">
      <ErrorBanner
        :message="errorMessage"
        :request-id="errorRequestId"
        retryable
        @retry="loadAlbums(1)"
      />
    </div>

    <AlbumGrid
      :albums="albums"
      :loading="loading"
      :can-edit="canEditAlbums"
      @open="openAlbum"
      @rename="openRenameDialog"
      @delete="openDeleteDialog"
    />

    <div v-if="hasMore && !loading" class="mt-6 flex justify-center">
      <Button variant="outline" :disabled="loadingMore" @click="loadMore">
        {{ loadingMore ? 'Loading...' : 'Load more albums' }}
      </Button>
    </div>

    <EmptyState
      v-if="!loading && albums.length === 0 && !errorMessage"
      icon="folder"
      title="No albums yet"
      description="Create an album to organize your favorite photos and videos."
    >
      <Button v-if="canEditAlbums" @click="openCreateDialog">
        <Plus class="h-4 w-4" />
        <span>Create Album</span>
      </Button>
    </EmptyState>

    <AlbumEditorDialog
      :open="editorOpen"
      :mode="editorMode"
      :initial-name="editorTargetName"
      :submitting="editorSubmitting"
      :error="editorError"
      @submit="submitEditor"
      @close="editorOpen = false"
    />

    <ConfirmDialog
      :open="deleteOpen"
      title="Delete Album"
      :description="`Delete album '${deleteTargetName}'? Photos and videos in your archive will not be deleted.`"
      confirm-label="Delete"
      destructive
      :submitting="deleteSubmitting"
      @confirm="confirmDelete"
      @cancel="deleteOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { navigateTo } from '#imports'
import { Plus } from 'lucide-vue-next'
import ConfirmDialog from '../../components/common/ConfirmDialog.vue'
import EmptyState from '../../components/common/EmptyState.vue'
import ErrorBanner from '../../components/common/ErrorBanner.vue'
import AlbumEditorDialog from '../../components/organisms/AlbumEditorDialog.vue'
import AlbumGrid from '../../components/organisms/AlbumGrid.vue'
import PageHeader from '../../components/organisms/PageHeader.vue'
import Button from '../../components/ui/Button.vue'
import { PhotosphereApiError, usePhotosphereApi } from '../../composables/usePhotosphereApi'
import { useAuthStore } from '../../stores/auth'
import type { AlbumSummary } from '../../types'

const authStore = useAuthStore()
const { initialized, isAuthenticated, canEditAlbums } = storeToRefs(authStore)
const { listAlbums, createAlbum, updateAlbum, deleteAlbum } = usePhotosphereApi()

const albums = ref<AlbumSummary[]>([])
const totalCount = ref(0)
const page = ref(1)
const hasMore = ref(false)
const loading = ref(false)
const loadingMore = ref(false)
const errorMessage = ref('')
const errorRequestId = ref<string | undefined>(undefined)

const editorOpen = ref(false)
const editorMode = ref<'create' | 'rename'>('create')
const editorTargetName = ref('')
const editorSubmitting = ref(false)
const editorError = ref('')

const deleteOpen = ref(false)
const deleteTargetName = ref('')
const deleteSubmitting = ref(false)

const loadAlbums = async (targetPage = 1) => {
  if (!isAuthenticated.value) return
  if (targetPage === 1) {
    loading.value = true
  } else {
    loadingMore.value = true
  }
  errorMessage.value = ''
  errorRequestId.value = undefined
  try {
    const res = await listAlbums(targetPage, 20)
    if (targetPage === 1) {
      albums.value = res.items
    } else {
      albums.value.push(...res.items)
    }
    page.value = res.page
    totalCount.value = res.totalCount
    hasMore.value = res.hasMore
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Failed to load albums'
    errorRequestId.value = error instanceof PhotosphereApiError ? error.requestId : undefined
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

const loadMore = () => loadAlbums(page.value + 1)

const openAlbum = async (name: string) => {
  await navigateTo(`/albums/${encodeURIComponent(name)}`)
}

const openCreateDialog = () => {
  editorMode.value = 'create'
  editorTargetName.value = ''
  editorError.value = ''
  editorOpen.value = true
}

const openRenameDialog = (name: string) => {
  editorMode.value = 'rename'
  editorTargetName.value = name
  editorError.value = ''
  editorOpen.value = true
}

const submitEditor = async (name: string) => {
  editorSubmitting.value = true
  editorError.value = ''
  try {
    if (editorMode.value === 'create') {
      await createAlbum(name, [])
    } else {
      await updateAlbum(editorTargetName.value, { newName: name })
    }
    editorOpen.value = false
    await loadAlbums(1)
  } catch (error) {
    editorError.value = error instanceof Error ? error.message : 'Failed to save album'
  } finally {
    editorSubmitting.value = false
  }
}

const openDeleteDialog = (name: string) => {
  deleteTargetName.value = name
  deleteOpen.value = true
}

const confirmDelete = async () => {
  deleteSubmitting.value = true
  try {
    await deleteAlbum(deleteTargetName.value)
    deleteOpen.value = false
    await loadAlbums(1)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Failed to delete album'
    deleteOpen.value = false
  } finally {
    deleteSubmitting.value = false
  }
}

watch(
  [initialized, isAuthenticated],
  ([isInit, isAuthed]) => {
    if (isInit && isAuthed) {
      loadAlbums(1)
    }
  },
  { immediate: true }
)
</script>

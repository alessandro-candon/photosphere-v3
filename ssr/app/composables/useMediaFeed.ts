import { getCurrentScope, onScopeDispose, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useAuthStore } from '../stores/auth'
import type { GalleryFilters, MediaGridItem } from '../types'
import { useMediaLightbox } from './useMediaLightbox'
import { PhotosphereApiError, usePhotosphereApi } from './usePhotosphereApi'

const isAbortError = (error: unknown): boolean =>
  error instanceof DOMException && error.name === 'AbortError'

export const useMediaFeed = (getFilters: () => GalleryFilters, pageSize = 50) => {
  const authStore = useAuthStore()
  const { initialized, isAuthenticated, preferredLang } = storeToRefs(authStore)
  const { listFiles } = usePhotosphereApi()

  const items = ref<MediaGridItem[]>([])
  const totalCount = ref(0)
  const page = ref(1)
  const hasMore = ref(false)
  const loading = ref(false)
  const loadingMore = ref(false)
  const errorMessage = ref('')
  const errorRequestId = ref<string | undefined>(undefined)

  let activeInitialController: AbortController | null = null
  let activeMoreController: AbortController | null = null

  const cancelInFlight = () => {
    if (activeInitialController) {
      activeInitialController.abort()
      activeInitialController = null
    }
    if (activeMoreController) {
      activeMoreController.abort()
      activeMoreController = null
    }
  }

  const loadInitial = async () => {
    if (!isAuthenticated.value) return
    cancelInFlight()
    lightbox.closeLightbox()

    const controller = new AbortController()
    activeInitialController = controller
    loading.value = true
    loadingMore.value = false
    errorMessage.value = ''
    errorRequestId.value = undefined
    page.value = 1

    try {
      const response = await listFiles(getFilters(), 1, pageSize, { signal: controller.signal })
      if (activeInitialController !== controller) return
      items.value = response.items
      totalCount.value = response.totalCount
      hasMore.value = response.hasMore
    } catch (error) {
      if (isAbortError(error)) return
      if (activeInitialController !== controller) return
      errorMessage.value = error instanceof Error ? error.message : 'Failed to load media'
      errorRequestId.value = error instanceof PhotosphereApiError ? error.requestId : undefined
    } finally {
      if (activeInitialController === controller) {
        loading.value = false
        activeInitialController = null
      }
    }
  }

  const loadMore = async () => {
    if (!isAuthenticated.value || loading.value || loadingMore.value || !hasMore.value) {
      return
    }
    const controller = new AbortController()
    activeMoreController = controller
    loadingMore.value = true
    const nextPage = page.value + 1

    try {
      const response = await listFiles(getFilters(), nextPage, pageSize, {
        signal: controller.signal,
      })
      if (activeMoreController !== controller) return
      items.value.push(...response.items)
      page.value = nextPage
      totalCount.value = response.totalCount
      hasMore.value = response.hasMore
    } catch (error) {
      if (isAbortError(error)) return
      if (activeMoreController !== controller) return
      errorMessage.value = error instanceof Error ? error.message : 'Failed to load more media'
      errorRequestId.value = error instanceof PhotosphereApiError ? error.requestId : undefined
    } finally {
      if (activeMoreController === controller) {
        loadingMore.value = false
        activeMoreController = null
      }
    }
  }

  const lightbox = useMediaLightbox({
    items,
    hasMore,
    loadMore,
  })

  watch(
    [initialized, isAuthenticated, preferredLang, () => JSON.stringify(getFilters())],
    async ([isInit, isAuthed]) => {
      if (!isInit || !isAuthed) return
      await loadInitial()
    },
    { immediate: true }
  )

  if (getCurrentScope()) {
    onScopeDispose(() => {
      cancelInFlight()
    })
  }

  return {
    items,
    totalCount,
    hasMore,
    loading,
    loadingMore,
    errorMessage,
    errorRequestId,
    activeItem: lightbox.activeItem,
    activeDetail: lightbox.activeDetail,
    detailLoading: lightbox.detailLoading,
    hasPrev: lightbox.hasPrev,
    hasNext: lightbox.hasNext,
    loadInitial,
    loadMore,
    openLightbox: lightbox.openLightbox,
    closeLightbox: lightbox.closeLightbox,
    prevItem: lightbox.prevItem,
    nextItem: lightbox.nextItem,
  }
}

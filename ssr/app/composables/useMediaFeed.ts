import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useAuthStore } from '../stores/auth'
import type { GalleryFilters, MediaDetail, MediaGridItem } from '../types'
import { PhotosphereApiError, usePhotosphereApi } from './usePhotosphereApi'

export const useMediaFeed = (getFilters: () => GalleryFilters, pageSize = 50) => {
  const authStore = useAuthStore()
  const { initialized, isAuthenticated, preferredLang } = storeToRefs(authStore)
  const { listFiles, getFileDetail } = usePhotosphereApi()

  const items = ref<MediaGridItem[]>([])
  const totalCount = ref(0)
  const page = ref(1)
  const hasMore = ref(false)
  const loading = ref(false)
  const loadingMore = ref(false)
  const errorMessage = ref('')
  const errorRequestId = ref<string | undefined>(undefined)

  const lightboxIndex = ref<number | null>(null)
  const activeDetail = ref<MediaDetail | null>(null)
  const detailLoading = ref(false)

  const activeItem = computed(() => {
    if (lightboxIndex.value === null) return null
    return items.value[lightboxIndex.value] || null
  })

  const hasPrev = computed(() => lightboxIndex.value !== null && lightboxIndex.value > 0)
  const hasNext = computed(
    () =>
      lightboxIndex.value !== null &&
      (lightboxIndex.value < items.value.length - 1 || hasMore.value)
  )

  const loadInitial = async () => {
    if (!isAuthenticated.value) return
    loading.value = true
    errorMessage.value = ''
    errorRequestId.value = undefined
    page.value = 1

    try {
      const response = await listFiles(getFilters(), 1, pageSize)
      items.value = response.items
      totalCount.value = response.totalCount
      hasMore.value = response.hasMore
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : 'Failed to load media'
      errorRequestId.value = error instanceof PhotosphereApiError ? error.requestId : undefined
    } finally {
      loading.value = false
    }
  }

  const loadMore = async () => {
    if (!isAuthenticated.value || loading.value || loadingMore.value || !hasMore.value) {
      return
    }
    loadingMore.value = true
    const nextPage = page.value + 1
    try {
      const response = await listFiles(getFilters(), nextPage, pageSize)
      items.value.push(...response.items)
      page.value = nextPage
      totalCount.value = response.totalCount
      hasMore.value = response.hasMore
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : 'Failed to load more media'
      errorRequestId.value = error instanceof PhotosphereApiError ? error.requestId : undefined
    } finally {
      loadingMore.value = false
    }
  }

  const loadDetailForIndex = async (idx: number) => {
    const target = items.value[idx]
    if (!target) {
      activeDetail.value = null
      return
    }
    detailLoading.value = true
    activeDetail.value = null
    try {
      activeDetail.value = await getFileDetail(target.hash)
    } catch {
      activeDetail.value = null
    } finally {
      detailLoading.value = false
    }
  }

  const openLightbox = async (item: MediaGridItem) => {
    const idx = items.value.findIndex((entry) => entry.hash === item.hash)
    if (idx < 0) return
    lightboxIndex.value = idx
    await loadDetailForIndex(idx)
  }

  const closeLightbox = () => {
    lightboxIndex.value = null
    activeDetail.value = null
  }

  const prevItem = async () => {
    if (lightboxIndex.value === null || lightboxIndex.value <= 0) return
    const nextIdx = lightboxIndex.value - 1
    lightboxIndex.value = nextIdx
    await loadDetailForIndex(nextIdx)
  }

  const nextItem = async () => {
    if (lightboxIndex.value === null) return
    const nextIdx = lightboxIndex.value + 1
    if (nextIdx >= items.value.length && hasMore.value) {
      await loadMore()
    }
    if (nextIdx < items.value.length) {
      lightboxIndex.value = nextIdx
      await loadDetailForIndex(nextIdx)
    }
  }

  watch(
    [initialized, isAuthenticated, preferredLang, () => JSON.stringify(getFilters())],
    async ([isInit, isAuthed]) => {
      if (!isInit || !isAuthed) return
      await loadInitial()
    },
    { immediate: true }
  )

  return {
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
  }
}

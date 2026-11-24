import { computed, ref, watch, type Ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useAuthStore } from '../stores/auth'
import type { MediaDetail, MediaGridItem } from '../types'
import { usePhotosphereApi } from './usePhotosphereApi'

export interface UseMediaLightboxOptions {
  items: Ref<MediaGridItem[]>
  hasMore?: Ref<boolean>
  loadMore?: () => Promise<void> | void
}

export const useMediaLightbox = (options: UseMediaLightboxOptions) => {
  const authStore = useAuthStore()
  const { preferredLang } = storeToRefs(authStore)
  const { getFileDetail } = usePhotosphereApi()

  const lightboxIndex = ref<number | null>(null)
  const detailCache = ref<Record<string, MediaDetail>>({})
  const detailLoading = ref(false)

  const activeItem = computed<MediaGridItem | null>(() => {
    if (lightboxIndex.value === null) return null
    return options.items.value[lightboxIndex.value] ?? null
  })

  const activeDetail = computed<MediaDetail | null>(() => {
    const item = activeItem.value
    return item ? (detailCache.value[item.hash] ?? null) : null
  })

  const hasPrev = computed(() => lightboxIndex.value !== null && lightboxIndex.value > 0)
  const hasNext = computed(
    () =>
      lightboxIndex.value !== null &&
      (lightboxIndex.value < options.items.value.length - 1 || Boolean(options.hasMore?.value))
  )

  const loadDetailForHash = async (hash: string) => {
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

  const openLightbox = async (target: MediaGridItem | number) => {
    const idx =
      typeof target === 'number'
        ? target
        : options.items.value.findIndex((entry) => entry.hash === target.hash)
    if (idx < 0 || idx >= options.items.value.length) return
    lightboxIndex.value = idx
    const item = options.items.value[idx]
    if (item) {
      await loadDetailForHash(item.hash)
    }
  }

  const closeLightbox = () => {
    lightboxIndex.value = null
  }

  const prevItem = async () => {
    if (!hasPrev.value || lightboxIndex.value === null) return
    await openLightbox(lightboxIndex.value - 1)
  }

  const nextItem = async () => {
    if (lightboxIndex.value === null) return
    const nextIdx = lightboxIndex.value + 1
    if (nextIdx >= options.items.value.length && options.hasMore?.value && options.loadMore) {
      await options.loadMore()
    }
    if (nextIdx < options.items.value.length) {
      await openLightbox(nextIdx)
    }
  }

  watch(preferredLang, () => {
    detailCache.value = {}
    const current = activeItem.value
    if (current) {
      void loadDetailForHash(current.hash)
    }
  })

  return {
    lightboxIndex,
    activeItem,
    activeDetail,
    detailLoading,
    hasPrev,
    hasNext,
    openLightbox,
    closeLightbox,
    prevItem,
    nextItem,
  }
}

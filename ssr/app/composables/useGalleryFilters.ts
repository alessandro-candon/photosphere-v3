import { computed } from 'vue'
import { navigateTo, useRoute } from '#imports'
import { VALID_FILE_TYPES } from '#shared/constants'
import type { GalleryFilters, MediaFileType, SearchFieldMode } from '../types'

const firstString = (value: unknown): string | undefined => {
  if (typeof value === 'string') return value.trim() || undefined
  if (Array.isArray(value) && typeof value[0] === 'string') return value[0].trim() || undefined
  return undefined
}

const optionalNumber = (value: unknown): number | undefined => {
  const raw = firstString(value)
  if (!raw) return undefined
  const num = Number(raw)
  return Number.isFinite(num) ? num : undefined
}

const optionalNonNegativeInt = (value: unknown): number | undefined => {
  const raw = firstString(value)
  if (!raw) return undefined
  const num = Number(raw)
  return Number.isInteger(num) && num >= 0 ? num : undefined
}

const parseSearchField = (value: unknown): SearchFieldMode | undefined => {
  const raw = firstString(value)?.toLowerCase()
  if (raw === 'labels' || raw === 'tags') return 'labels'
  if (raw === 'captions') return 'captions'
  return undefined
}

export const useGalleryFilters = () => {
  const route = useRoute()

  const filters = computed<GalleryFilters>(() => {
    const q = firstString(route.query.q)
    const searchField = parseSearchField(route.query.searchField)
    const labelIndex = optionalNonNegativeInt(route.query.labelIndex)
    const captionIndex = optionalNonNegativeInt(route.query.captionIndex)
    const rawType = firstString(route.query.fileType)?.toUpperCase()
    const fileType =
      rawType && VALID_FILE_TYPES.has(rawType as MediaFileType)
        ? (rawType as MediaFileType)
        : undefined
    const dateFrom = firstString(route.query.dateFrom)
    const dateTo = firstString(route.query.dateTo)
    const memoryDate = firstString(route.query.memoryDate)
    const album = firstString(route.query.album)
    const lat = optionalNumber(route.query.lat)
    const lng = optionalNumber(route.query.lng)
    const radiusKm = optionalNumber(route.query.radiusKm)
    const place = firstString(route.query.place)
    const notInAlbum = firstString(route.query.notInAlbum) === 'true'

    return {
      ...(q ? { q } : {}),
      ...(searchField ? { searchField } : {}),
      ...(labelIndex !== undefined ? { labelIndex } : {}),
      ...(captionIndex !== undefined ? { captionIndex } : {}),
      ...(fileType ? { fileType } : {}),
      ...(dateFrom ? { dateFrom } : {}),
      ...(dateTo ? { dateTo } : {}),
      ...(memoryDate ? { memoryDate } : {}),
      ...(album ? { album } : {}),
      ...(lat !== undefined && lng !== undefined ? { lat, lng } : {}),
      ...(radiusKm !== undefined ? { radiusKm } : {}),
      ...(place ? { place } : {}),
      ...(notInAlbum ? { notInAlbum: true } : {}),
    }
  })

  const applyFilters = async (next: GalleryFilters): Promise<void> => {
    const query: Record<string, string> = {}
    if (next.q?.trim()) query.q = next.q.trim()
    if (next.searchField) query.searchField = next.searchField
    if (next.labelIndex !== undefined) query.labelIndex = String(next.labelIndex)
    if (next.captionIndex !== undefined) query.captionIndex = String(next.captionIndex)
    if (next.fileType) query.fileType = next.fileType
    if (next.dateFrom) query.dateFrom = next.dateFrom
    if (next.dateTo) query.dateTo = next.dateTo
    if (next.memoryDate) query.memoryDate = next.memoryDate
    if (next.album) query.album = next.album
    if (next.notInAlbum) query.notInAlbum = 'true'
    if (next.lat !== undefined && next.lng !== undefined) {
      query.lat = String(next.lat)
      query.lng = String(next.lng)
      query.radiusKm = String(next.radiusKm ?? 10)
      if (next.place) query.place = next.place
    }
    await navigateTo({ path: route.path, query })
  }

  const clearAllFilters = async (): Promise<void> => {
    await navigateTo({ path: route.path, query: {} })
  }

  return {
    filters,
    applyFilters,
    clearAllFilters,
  }
}

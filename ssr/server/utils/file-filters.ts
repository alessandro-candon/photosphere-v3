import type { HydratedMediaItem, MediaFileType } from '../types/cache'

export interface MediaQueryFilters {
  q?: string
  fileType?: MediaFileType | 'ALL'
  dateFrom?: number
  dateTo?: number
  hasLocation?: boolean
  albumHashes?: Set<string>
}

export const normalizeLanguageCode = (raw: unknown, fallback = 'en'): string => {
  if (typeof raw !== 'string') {
    return fallback
  }
  const clean = raw.trim().toLowerCase()
  return /^[a-z]{2}(-[a-z]{2})?$/.test(clean) ? clean : fallback
}

export const matchesMediaFilters = (
  item: HydratedMediaItem,
  filters: MediaQueryFilters
): boolean => {
  if (filters.albumHashes && !filters.albumHashes.has(item.hash)) {
    return false
  }
  if (filters.fileType && filters.fileType !== 'ALL' && item.fileType !== filters.fileType) {
    return false
  }
  if (filters.hasLocation && (item.latitude === null || item.longitude === null)) {
    return false
  }
  if (
    filters.dateFrom !== undefined &&
    (item.createdAtTimestamp === null || item.createdAtTimestamp < filters.dateFrom)
  ) {
    return false
  }
  if (
    filters.dateTo !== undefined &&
    (item.createdAtTimestamp === null || item.createdAtTimestamp > filters.dateTo)
  ) {
    return false
  }
  if (filters.q) {
    const query = filters.q.trim().toLowerCase()
    if (query.length > 0) {
      const inHash = item.hash.toLowerCase().includes(query)
      const inCaption = (item.caption || '').toLowerCase().includes(query)
      const inLabels = item.labels.some((lbl) => lbl.toLowerCase().includes(query))
      const inSource = item.proxyUrls.sourceUrl.toLowerCase().includes(query)
      if (!inHash && !inCaption && !inLabels && !inSource) {
        return false
      }
    }
  }
  return true
}

export const parsePagination = (
  rawPage: unknown,
  rawLimit: unknown
): { page: number; limit: number } => {
  const parsedPage = Number.parseInt(String(rawPage ?? '1'), 10)
  const parsedLimit = Number.parseInt(String(rawLimit ?? '60'), 10)
  const page = Number.isFinite(parsedPage) && parsedPage > 0 ? parsedPage : 1
  const limit = Number.isFinite(parsedLimit) && parsedLimit > 0 ? Math.min(parsedLimit, 200) : 60
  return { page, limit }
}

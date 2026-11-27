export type MediaFileType = 'FILE' | 'IMAGE' | 'VIDEO'
export type GeohashPrecision = 2 | 3 | 4 | 5 | 6
export type SearchFieldMode = 'labels' | 'captions'
export type MediaSortOrder = 'date' | 'distance'
export type BasemapStyle = 'dark' | 'light' | 'satellite'
export type HeatmapDataMode = 'geohash' | 'raw'
export type HeatmapPointTuple = [number, number, number]

export const SHA1_REGEX = /^[0-9a-f]{40}$/
export const UINT_KEY_REGEX = /^(0|[1-9][0-9]*)$/
export const MONTH_DAY_REGEX = /^\d{2}-\d{2}$/
export const DATE_ONLY_REGEX = /^\d{4}-\d{2}-\d{2}$/
export const LANG_REGEX = /^[a-z]{2}(-[a-z]{2})?$/i

export const VALID_FILE_TYPES = new Set<MediaFileType>(['FILE', 'IMAGE', 'VIDEO'])
export const GEOHASH_PRECISIONS: readonly GeohashPrecision[] = [2, 3, 4, 5, 6] as const

export const normalizeAllowedEmails = (allowed: string[] | string | undefined): string[] => {
  if (!allowed) {
    return []
  }
  const items = Array.isArray(allowed) ? allowed : allowed.split(',')
  return items.map((email) => email.trim().toLowerCase()).filter(Boolean)
}

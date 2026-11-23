import type {
  AlbumRecord,
  LanguageDictionaries,
  MediaDatabaseSnapshot,
  MediaFileType,
  RawMediaRecord,
} from '../types/cache'
import { toEpochMilliseconds } from './file-database-cache'

export type SearchFieldMode = 'labels' | 'captions'

export interface MediaFilterParams {
  q?: string
  searchField?: SearchFieldMode
  labelIndex?: number
  captionIndex?: number
  fileType?: MediaFileType
  dateFrom?: string
  dateTo?: string
  memoryDate?: string
  album?: string
  notInAlbum?: boolean
  lat?: number
  lng?: number
  radiusKm?: number
}

export interface MediaGridItemDto {
  hash: string
  fileType: MediaFileType
  createdAt: string | null
  createdAtTimestamp: number | null
  fileName: string
  hasThumbnail: boolean
  thumbnailUrl: string | null
  sourceUrl: string
}

export interface MediaDetailDto extends MediaGridItemDto {
  latitude: number | null
  longitude: number | null
  geohash: string | null
  labels: string[]
  caption: string | null
}

const EARTH_RADIUS_KM = 6371
const DATE_ONLY_REGEX = /^\d{4}-\d{2}-\d{2}$/
const MONTH_DAY_REGEX = /^\d{2}-\d{2}$/

export const extractFileName = (gsUri: string): string => {
  const clean = gsUri.split('?')[0] || gsUri
  const idx = clean.lastIndexOf('/')
  return idx >= 0 ? clean.slice(idx + 1) || clean : clean
}

export const haversineDistanceKm = (
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number => {
  const toRad = (deg: number) => (deg * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2)
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  return EARTH_RADIUS_KM * c
}

const parseDateBoundMs = (raw: string | undefined, bound: 'start' | 'end'): number | null => {
  if (!raw) return null
  const trimmed = raw.trim()
  if (!trimmed) return null
  if (DATE_ONLY_REGEX.test(trimmed)) {
    const suffix = bound === 'start' ? 'T00:00:00.000Z' : 'T23:59:59.999Z'
    const parsed = Date.parse(`${trimmed}${suffix}`)
    return Number.isNaN(parsed) ? null : parsed
  }
  const parsed = Date.parse(trimmed)
  return Number.isNaN(parsed) ? null : parsed
}

export const filterMediaHashes = (
  snapshot: MediaDatabaseSnapshot,
  filters: MediaFilterParams,
  options: { dicts?: LanguageDictionaries; albums?: AlbumRecord[] } = {}
): string[] => {
  let baseHashes = snapshot.sortedHashes
  if (filters.memoryDate) {
    if (!MONTH_DAY_REGEX.test(filters.memoryDate)) {
      return []
    }
    baseHashes = snapshot.byMonthDay[filters.memoryDate] || []
  }

  let requiredAlbumSet: Set<string> | null = null
  if (filters.album) {
    const targetName = filters.album.trim()
    const albums = options.albums || []
    const matched =
      albums.find((a) => a.name === targetName) ||
      albums.find((a) => a.name.trim().toLowerCase() === targetName.toLowerCase())
    if (!matched) {
      return []
    }
    requiredAlbumSet = new Set(matched.hashes)
  }

  let excludedAlbumSet: Set<string> | null = null
  if (filters.notInAlbum) {
    excludedAlbumSet = new Set<string>()
    for (const album of options.albums || []) {
      for (const h of album.hashes) {
        excludedAlbumSet.add(h)
      }
    }
  }

  const startMs = parseDateBoundMs(filters.dateFrom, 'start')
  const endMs = parseDateBoundMs(filters.dateTo, 'end')
  const hasDateBounds = startMs !== null || endMs !== null

  const hasLocationFilter =
    typeof filters.lat === 'number' &&
    Number.isFinite(filters.lat) &&
    typeof filters.lng === 'number' &&
    Number.isFinite(filters.lng)
  const radiusKm = hasLocationFilter ? Math.min(Math.max(filters.radiusKm ?? 10, 0.1), 1000) : 10
  const latDelta = hasLocationFilter ? radiusKm / 111.32 : 0
  const cosLat = hasLocationFilter
    ? Math.max(Math.abs(Math.cos((filters.lat! * Math.PI) / 180)), 0.01)
    : 1
  const lngDelta = hasLocationFilter ? radiusKm / (111.32 * cosLat) : 0

  const hasLabelIndex =
    typeof filters.labelIndex === 'number' && Number.isInteger(filters.labelIndex)
  const hasCaptionIndex =
    typeof filters.captionIndex === 'number' && Number.isInteger(filters.captionIndex)

  const needle = (filters.q || '').trim().toLowerCase()
  const dicts = options.dicts

  const result: string[] = []
  for (const hash of baseHashes) {
    const rec = snapshot.recordsByHash[hash]
    if (!rec) continue

    if (filters.fileType && rec.file_type !== filters.fileType) {
      continue
    }

    if (hasLabelIndex && !rec.label_indexes.includes(filters.labelIndex!)) {
      continue
    }

    if (hasCaptionIndex && rec.caption_index !== filters.captionIndex!) {
      continue
    }

    if (requiredAlbumSet && !requiredAlbumSet.has(hash)) {
      continue
    }

    if (excludedAlbumSet && excludedAlbumSet.has(hash)) {
      continue
    }

    if (hasDateBounds) {
      if (
        typeof rec.created_at_timestamp !== 'number' ||
        !Number.isFinite(rec.created_at_timestamp)
      ) {
        continue
      }
      const tsMs = toEpochMilliseconds(rec.created_at_timestamp)
      if (startMs !== null && tsMs < startMs) continue
      if (endMs !== null && tsMs > endMs) continue
    }

    if (hasLocationFilter) {
      if (
        typeof rec.latitude !== 'number' ||
        !Number.isFinite(rec.latitude) ||
        typeof rec.longitude !== 'number' ||
        !Number.isFinite(rec.longitude)
      ) {
        continue
      }
      if (
        Math.abs(rec.latitude - filters.lat!) > latDelta ||
        Math.abs(rec.longitude - filters.lng!) > lngDelta
      ) {
        continue
      }
      if (haversineDistanceKm(filters.lat!, filters.lng!, rec.latitude, rec.longitude) > radiusKm) {
        continue
      }
    }

    if (needle) {
      let matched = false

      if (filters.searchField === 'labels') {
        if (dicts) {
          for (const labelIndex of rec.label_indexes) {
            const label = dicts.labels[String(labelIndex)]
            if (label && label.toLowerCase().includes(needle)) {
              matched = true
              break
            }
          }
        }
      } else if (filters.searchField === 'captions') {
        if (dicts && rec.caption_index !== null) {
          const caption = dicts.captions[String(rec.caption_index)]
          if (caption && caption.toLowerCase().includes(needle)) {
            matched = true
          }
        }
      } else {
        const fileName = extractFileName(rec.source_bucket_uri).toLowerCase()
        matched = fileName.includes(needle)

        if (!matched && dicts) {
          for (const labelIndex of rec.label_indexes) {
            const label = dicts.labels[String(labelIndex)]
            if (label && label.toLowerCase().includes(needle)) {
              matched = true
              break
            }
          }
          if (!matched && rec.caption_index !== null) {
            const caption = dicts.captions[String(rec.caption_index)]
            if (caption && caption.toLowerCase().includes(needle)) {
              matched = true
            }
          }
        }
      }

      if (!matched) {
        continue
      }
    }

    result.push(hash)
  }

  return result
}

export const toMediaGridItem = (rec: RawMediaRecord): MediaGridItemDto => {
  const hasThumbnail = rec.thumbnail_bucket_uri !== null || rec.file_type === 'IMAGE'
  return {
    hash: rec.hash,
    fileType: rec.file_type,
    createdAt: rec.created_at,
    createdAtTimestamp: rec.created_at_timestamp,
    fileName: extractFileName(rec.source_bucket_uri),
    hasThumbnail,
    thumbnailUrl: hasThumbnail ? `/api/media/${rec.hash}?variant=thumbnail` : null,
    sourceUrl: `/api/media/${rec.hash}?variant=source`,
  }
}

export const toMediaDetail = (rec: RawMediaRecord, dicts: LanguageDictionaries): MediaDetailDto => {
  const labels: string[] = []
  for (const labelIndex of rec.label_indexes) {
    const label = dicts.labels[String(labelIndex)]
    if (label) {
      labels.push(label)
    }
  }
  const caption =
    rec.caption_index !== null ? (dicts.captions[String(rec.caption_index)] ?? null) : null

  return {
    ...toMediaGridItem(rec),
    latitude: rec.latitude,
    longitude: rec.longitude,
    geohash: rec.geohash,
    labels,
    caption,
  }
}

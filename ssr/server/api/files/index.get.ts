import { createError, defineEventHandler, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import type { MediaFileType } from '../../types/cache'
import { getAlbums } from '../../utils/albums-cache'
import {
  getLanguageDictionaries,
  getMediaDatabase,
  normalizeLanguageCode,
} from '../../utils/file-database-cache'
import {
  filterMediaHashes,
  sortMediaHashesByDistance,
  toMediaGridItem,
  type MediaFilterParams,
  type SearchFieldMode,
} from '../../utils/file-filters'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

const VALID_FILE_TYPES = new Set<MediaFileType>(['FILE', 'IMAGE', 'VIDEO'])

const parseOptionalNumber = (raw: unknown): number | undefined => {
  if (typeof raw !== 'string' || !raw.trim()) return undefined
  const num = Number(raw)
  return Number.isFinite(num) ? num : undefined
}

const parseOptionalNonNegativeInt = (raw: unknown): number | undefined => {
  if (typeof raw !== 'string' || !raw.trim()) return undefined
  const num = Number(raw.trim())
  return Number.isInteger(num) && num >= 0 ? num : undefined
}

const parseSearchField = (raw: unknown): SearchFieldMode | undefined => {
  if (typeof raw !== 'string' || !raw.trim()) return undefined
  const clean = raw.trim().toLowerCase()
  if (clean === 'labels' || clean === 'tags') return 'labels'
  if (clean === 'captions') return 'captions'
  throw createError({
    statusCode: 400,
    statusMessage: "Invalid searchField parameter: expected 'labels', 'tags', or 'captions'",
  })
}

const parseSortOrder = (raw: unknown): 'date' | 'distance' => {
  if (typeof raw !== 'string' || !raw.trim()) return 'date'
  const clean = raw.trim().toLowerCase()
  if (clean === 'date' || clean === 'distance') return clean
  throw createError({
    statusCode: 400,
    statusMessage: "Invalid sort parameter: expected 'date' or 'distance'",
  })
}

export default defineEventHandler(async (event) => {
  const cfg = useRuntimeConfig(event)
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const query = getQuery(event)

  const parsedPage = parseInt(String(query.page || '1'), 10)
  const page = Number.isFinite(parsedPage) && parsedPage >= 1 ? parsedPage : 1
  const parsedLimit = parseInt(String(query.limit || '50'), 10)
  const limit = Math.min(Math.max(Number.isFinite(parsedLimit) ? parsedLimit : 50, 1), 200)
  const skip = (page - 1) * limit
  const sort = parseSortOrder(query.sort)

  const rawFileType = typeof query.fileType === 'string' ? query.fileType.trim().toUpperCase() : ''
  let fileType: MediaFileType | undefined
  if (rawFileType) {
    if (!VALID_FILE_TYPES.has(rawFileType as MediaFileType)) {
      throw createError({
        statusCode: 400,
        statusMessage: `Invalid fileType '${rawFileType}'`,
      })
    }
    fileType = rawFileType as MediaFileType
  }

  const q = typeof query.q === 'string' ? query.q.trim() : undefined
  const searchField = parseSearchField(query.searchField)
  const labelIndex = parseOptionalNonNegativeInt(query.labelIndex)
  const captionIndex = parseOptionalNonNegativeInt(query.captionIndex)
  const dateFrom = typeof query.dateFrom === 'string' ? query.dateFrom.trim() : undefined
  const dateTo = typeof query.dateTo === 'string' ? query.dateTo.trim() : undefined
  const memoryDate = typeof query.memoryDate === 'string' ? query.memoryDate.trim() : undefined
  const album = typeof query.album === 'string' ? query.album.trim() : undefined
  const notInAlbum = query.notInAlbum === 'true' || query.notInAlbum === '1'
  const lat = parseOptionalNumber(query.lat)
  const lng = parseOptionalNumber(query.lng)
  const radiusKm = parseOptionalNumber(query.radiusKm)

  const lang = normalizeLanguageCode(query.lang, cfg.public?.defaultLang || 'en')
  const dbFileName = cfg.database?.jsonFileName || 'photosphere_database_cloud.json'
  const labelsSuffix =
    cfg.database?.labelsJsonFileName || 'photosphere_image_labelling_database_cloud.json'
  const captionsSuffix =
    cfg.database?.captionsJsonFileName || 'photosphere_image_caption_database_cloud.json'
  const albumsFileName = cfg.database?.albumsJsonFileName || 'photosphere_albums.json'

  const [snapshot, dicts, albums] = await Promise.all([
    getMediaDatabase(idToken, { ...storageOpts, dbFileName }),
    q
      ? getLanguageDictionaries(lang, idToken, { ...storageOpts, labelsSuffix, captionsSuffix })
      : Promise.resolve(undefined),
    album || notInAlbum
      ? getAlbums(idToken, { ...storageOpts, albumsFileName })
      : Promise.resolve(undefined),
  ])

  const filters: MediaFilterParams = {
    q,
    searchField,
    labelIndex,
    captionIndex,
    fileType,
    dateFrom,
    dateTo,
    memoryDate,
    album,
    notInAlbum,
    lat,
    lng,
    radiusKm,
  }

  const matchingHashes = filterMediaHashes(snapshot, filters, { dicts, albums })

  if (sort === 'distance' && lat !== undefined && lng !== undefined) {
    const distanceSorted = sortMediaHashesByDistance(snapshot, matchingHashes, lat, lng)
    const totalCount = distanceSorted.length
    const paginatedEntries = distanceSorted.slice(skip, skip + limit)
    const items = paginatedEntries
      .map((entry) => {
        const rec = snapshot.recordsByHash[entry.hash]
        if (!rec) return null
        return toMediaGridItem(rec, Number(entry.distanceKm.toFixed(3)))
      })
      .filter((item): item is NonNullable<typeof item> => Boolean(item))

    return {
      items,
      totalCount,
      page,
      limit,
      hasMore: skip + limit < totalCount,
    }
  }

  const totalCount = matchingHashes.length
  const paginatedHashes = matchingHashes.slice(skip, skip + limit)
  const items = paginatedHashes
    .map((hash) => snapshot.recordsByHash[hash])
    .filter((rec): rec is NonNullable<typeof rec> => Boolean(rec))
    .map((rec) => toMediaGridItem(rec))

  return {
    items,
    totalCount,
    page,
    limit,
    hasMore: skip + limit < totalCount,
  }
})

import { createError, defineEventHandler, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import type { MediaFileType } from '../../types/cache'
import { getAlbums } from '../../utils/albums-cache'
import {
  getLanguageDictionaries,
  getMediaDatabase,
  normalizeLanguageCode,
} from '../../utils/file-database-cache'
import type { MediaFilterParams, SearchFieldMode } from '../../utils/file-filters'
import { aggregateViewportHeatmap, type HeatmapDataMode } from '../../utils/map-aggregation'
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

const parseDataMode = (raw: unknown): HeatmapDataMode => {
  if (typeof raw !== 'string' || !raw.trim()) return 'geohash'
  const clean = raw.trim().toLowerCase()
  if (clean === 'geohash' || clean === 'raw') return clean
  throw createError({
    statusCode: 400,
    statusMessage: "Invalid mode parameter: expected 'geohash' or 'raw'",
  })
}

export default defineEventHandler(async (event) => {
  const cfg = useRuntimeConfig(event)
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const query = getQuery(event)

  const north = parseOptionalNumber(query.north)
  const south = parseOptionalNumber(query.south)
  const east = parseOptionalNumber(query.east)
  const west = parseOptionalNumber(query.west)

  const parsedZoom = parseOptionalNumber(query.zoom)
  const zoom = parsedZoom !== undefined ? Math.min(Math.max(Math.round(parsedZoom), 2), 16) : 3
  const mode = parseDataMode(query.mode)

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
  }

  return aggregateViewportHeatmap(
    snapshot,
    { north, south, east, west, zoom, mode, filters },
    { dicts, albums }
  )
})

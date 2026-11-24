import { createError, getRouterParam, type H3Event } from 'h3'
import { useRuntimeConfig } from '#imports'
import {
  SHA1_REGEX,
  VALID_FILE_TYPES,
  type MediaFileType,
  type SearchFieldMode,
} from '#shared/index'
import type { AlbumRecord, LanguageDictionaries, MediaDatabaseSnapshot } from '../types/cache'
import { getAlbums } from './albums-cache'
import { getLanguageDictionaries, getMediaDatabase } from './file-database-cache'
import type { MediaFilterParams } from './file-filters'
import type { StorageOptions } from './storage-download'

export interface RuntimeDatabaseNames {
  dbFileName: string
  labelsSuffix: string
  captionsSuffix: string
  albumsFileName: string
}

export const getRuntimeDatabaseNames = (event: H3Event): RuntimeDatabaseNames => {
  const cfg = useRuntimeConfig(event)
  return {
    dbFileName: cfg.database?.jsonFileName || 'photosphere_database_cloud.json',
    labelsSuffix:
      cfg.database?.labelsJsonFileName || 'photosphere_image_labelling_database_cloud.json',
    captionsSuffix:
      cfg.database?.captionsJsonFileName || 'photosphere_image_caption_database_cloud.json',
    albumsFileName: cfg.database?.albumsJsonFileName || 'photosphere_albums.json',
  }
}

export const parseOptionalNumber = (raw: unknown): number | undefined => {
  if (typeof raw !== 'string' || !raw.trim()) return undefined
  const num = Number(raw)
  return Number.isFinite(num) ? num : undefined
}

export const parseOptionalNonNegativeInt = (raw: unknown): number | undefined => {
  if (typeof raw !== 'string' || !raw.trim()) return undefined
  const num = Number(raw.trim())
  return Number.isInteger(num) && num >= 0 ? num : undefined
}

export const parsePaginationParams = (
  query: Record<string, unknown>,
  defaultLimit = 50,
  maxLimit = 200
): { page: number; limit: number; skip: number } => {
  const parsedPage = parseInt(String(query.page || '1'), 10)
  const page = Number.isFinite(parsedPage) && parsedPage >= 1 ? parsedPage : 1
  const parsedLimit = parseInt(String(query.limit || String(defaultLimit)), 10)
  const limit = Math.min(
    Math.max(Number.isFinite(parsedLimit) ? parsedLimit : defaultLimit, 1),
    maxLimit
  )
  return {
    page,
    limit,
    skip: (page - 1) * limit,
  }
}

export const parseSha1Param = (event: H3Event, paramName = 'hash', label = 'file'): string => {
  const hash = getRouterParam(event, paramName) || ''
  if (!SHA1_REGEX.test(hash)) {
    throw createError({
      statusCode: 400,
      statusMessage: `Invalid ${label} hash parameter`,
    })
  }
  return hash
}

export const parseDecodedAlbumNameParam = (event: H3Event): string => {
  const rawName = getRouterParam(event, 'albumName') || ''
  try {
    return decodeURIComponent(rawName)
  } catch {
    throw createError({ statusCode: 400, statusMessage: 'Malformed albumName parameter' })
  }
}

export const parseSearchFieldParam = (
  raw: unknown,
  paramName = 'searchField'
): SearchFieldMode | undefined => {
  if (typeof raw !== 'string' || !raw.trim()) return undefined
  const clean = raw.trim().toLowerCase()
  if (clean === 'labels' || clean === 'tags') return 'labels'
  if (clean === 'captions') return 'captions'
  throw createError({
    statusCode: 400,
    statusMessage: `Invalid ${paramName} parameter: expected 'labels', 'tags', or 'captions'`,
  })
}

export const parseMediaFilterQuery = (
  query: Record<string, unknown>,
  options: { includeSpatial?: boolean } = {}
): MediaFilterParams => {
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
  const searchField = parseSearchFieldParam(query.searchField)
  const labelIndex = parseOptionalNonNegativeInt(query.labelIndex)
  const captionIndex = parseOptionalNonNegativeInt(query.captionIndex)
  const dateFrom = typeof query.dateFrom === 'string' ? query.dateFrom.trim() : undefined
  const dateTo = typeof query.dateTo === 'string' ? query.dateTo.trim() : undefined
  const memoryDate = typeof query.memoryDate === 'string' ? query.memoryDate.trim() : undefined
  const album = typeof query.album === 'string' ? query.album.trim() : undefined
  const notInAlbum = query.notInAlbum === 'true' || query.notInAlbum === '1'

  const base: MediaFilterParams = {
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

  if (options.includeSpatial) {
    base.lat = parseOptionalNumber(query.lat)
    base.lng = parseOptionalNumber(query.lng)
    base.radiusKm = parseOptionalNumber(query.radiusKm)
  }

  return base
}

export const loadFilterDependencies = async (
  idToken: string,
  storageOpts: StorageOptions,
  dbNames: RuntimeDatabaseNames,
  options: { lang: string; needDicts: boolean; needAlbums: boolean }
): Promise<{
  snapshot: MediaDatabaseSnapshot
  dicts: LanguageDictionaries | undefined
  albums: AlbumRecord[] | undefined
}> => {
  const [snapshot, dicts, albums] = await Promise.all([
    getMediaDatabase(idToken, { ...storageOpts, dbFileName: dbNames.dbFileName }),
    options.needDicts
      ? getLanguageDictionaries(options.lang, idToken, {
          ...storageOpts,
          labelsSuffix: dbNames.labelsSuffix,
          captionsSuffix: dbNames.captionsSuffix,
        })
      : Promise.resolve(undefined),
    options.needAlbums
      ? getAlbums(idToken, { ...storageOpts, albumsFileName: dbNames.albumsFileName })
      : Promise.resolve(undefined),
  ])
  return { snapshot, dicts, albums }
}

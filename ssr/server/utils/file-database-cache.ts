import { createError } from 'h3'
import type {
  HydratedMediaItem,
  KeyValueDictionary,
  LanguageDictionaries,
  MediaDatabaseSnapshot,
  RawMediaRecord,
} from '../types/cache'
import { loadJsonDatabase, type StorageOptions } from './storage-download'
import { toProxyUrl } from './url'

const SHA1_REGEX = /^[0-9a-f]{40}$/
const UINT_KEY_REGEX = /^(0|[1-9][0-9]*)$/
const VALID_FILE_TYPES = new Set(['FILE', 'IMAGE', 'VIDEO'])

let mediaDbCache: MediaDatabaseSnapshot | null = null
const languageDictCache = new Map<string, LanguageDictionaries>()

export const invalidateFileDatabaseCache = (): void => {
  mediaDbCache = null
  languageDictCache.clear()
}

export const validateMediaDatabasePayload = (raw: unknown): Record<string, RawMediaRecord> => {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw createError({
      statusCode: 500,
      statusMessage: 'Invalid photosphere_database_cloud.json: expected flat SHA-1 object map',
    })
  }

  const obj = raw as Record<string, unknown>
  if ('_default' in obj) {
    throw createError({
      statusCode: 500,
      statusMessage:
        'Legacy TinyDB _default wrapper detected in photosphere_database_cloud.json; run migration first',
    })
  }

  const verified: Record<string, RawMediaRecord> = {}
  for (const [key, value] of Object.entries(obj)) {
    if (!SHA1_REGEX.test(key)) {
      throw createError({
        statusCode: 500,
        statusMessage: `Invalid media database key '${key}': expected 40-char lowercase SHA-1`,
      })
    }
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw createError({
        statusCode: 500,
        statusMessage: `Invalid media record at key '${key}'`,
      })
    }
    const rec = value as Record<string, unknown>
    if ('local_file_path' in rec) {
      throw createError({
        statusCode: 500,
        statusMessage: `Forbidden legacy field 'local_file_path' present in record '${key}'`,
      })
    }
    if (rec.hash !== key) {
      throw createError({
        statusCode: 500,
        statusMessage: `Record hash mismatch for '${key}'`,
      })
    }
    if (typeof rec.source_bucket_uri !== 'string' || !rec.source_bucket_uri.startsWith('gs://')) {
      throw createError({
        statusCode: 500,
        statusMessage: `Invalid source_bucket_uri for record '${key}'`,
      })
    }
    if (typeof rec.file_type !== 'string' || !VALID_FILE_TYPES.has(rec.file_type)) {
      throw createError({
        statusCode: 500,
        statusMessage: `Invalid file_type '${String(rec.file_type)}' for record '${key}'`,
      })
    }
    if (!Array.isArray(rec.label_indexes) || rec.label_indexes.some((n) => !Number.isInteger(n))) {
      throw createError({
        statusCode: 500,
        statusMessage: `Invalid label_indexes for record '${key}'`,
      })
    }

    verified[key] = rec as unknown as RawMediaRecord
  }

  return verified
}

export const validateKeyValueDictionaryPayload = (raw: unknown): KeyValueDictionary => {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw createError({
      statusCode: 500,
      statusMessage: 'Invalid key-value dictionary JSON: expected object',
    })
  }
  const dict: KeyValueDictionary = {}
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (!UINT_KEY_REGEX.test(key) || typeof value !== 'string' || value.length === 0) {
      throw createError({
        statusCode: 500,
        statusMessage: `Invalid dictionary entry at key '${key}'`,
      })
    }
    dict[key] = value
  }
  return dict
}

export const sortMediaHashesDescending = (records: Record<string, RawMediaRecord>): string[] =>
  Object.keys(records).sort((a, b) => {
    const tsA = records[a]?.created_at_timestamp ?? -Infinity
    const tsB = records[b]?.created_at_timestamp ?? -Infinity
    if (tsB !== tsA) {
      return tsB - tsA
    }
    return a.localeCompare(b)
  })

export const getMediaDatabase = async (
  idToken: string,
  options?: StorageOptions & { dbFileName?: string }
): Promise<MediaDatabaseSnapshot> => {
  if (mediaDbCache && !options?.forceRefresh) {
    return mediaDbCache
  }
  const dbFileName = options?.dbFileName || 'photosphere_database_cloud.json'
  const recordsByHash = await loadJsonDatabase(
    dbFileName,
    dbFileName,
    idToken,
    validateMediaDatabasePayload,
    options
  )
  const snapshot: MediaDatabaseSnapshot = {
    recordsByHash,
    sortedHashes: sortMediaHashesDescending(recordsByHash),
    loadedAt: Date.now(),
  }
  mediaDbCache = snapshot
  return snapshot
}

const loadSingleDictionaryWithFallback = async (
  lang: string,
  suffixFileName: string,
  idToken: string,
  options?: StorageOptions
): Promise<KeyValueDictionary> => {
  const safeLang = /^[a-z]{2}(-[a-z]{2})?$/i.test(lang) ? lang.toLowerCase() : 'en'
  const primaryName = `${safeLang}_${suffixFileName}`
  try {
    return await loadJsonDatabase(
      primaryName,
      primaryName,
      idToken,
      validateKeyValueDictionaryPayload,
      options
    )
  } catch (error) {
    const statusCode = (error as { statusCode?: number }).statusCode
    if (statusCode === 404 && safeLang !== 'en') {
      const fallbackName = `en_${suffixFileName}`
      return await loadJsonDatabase(
        fallbackName,
        fallbackName,
        idToken,
        validateKeyValueDictionaryPayload,
        options
      )
    }
    if (statusCode === 404) {
      return {}
    }
    throw error
  }
}

export const getLanguageDictionaries = async (
  lang: string,
  idToken: string,
  options?: StorageOptions & { labelsSuffix?: string; captionsSuffix?: string }
): Promise<LanguageDictionaries> => {
  const safeLang = /^[a-z]{2}(-[a-z]{2})?$/i.test(lang) ? lang.toLowerCase() : 'en'
  const cached = languageDictCache.get(safeLang)
  if (cached && !options?.forceRefresh) {
    return cached
  }

  const labelsSuffix = options?.labelsSuffix || 'photosphere_image_labelling_database_cloud.json'
  const captionsSuffix = options?.captionsSuffix || 'photosphere_image_caption_database_cloud.json'

  const [labels, captions] = await Promise.all([
    loadSingleDictionaryWithFallback(safeLang, labelsSuffix, idToken, options),
    loadSingleDictionaryWithFallback(safeLang, captionsSuffix, idToken, options),
  ])

  const entry: LanguageDictionaries = {
    lang: safeLang,
    labels,
    captions,
    loadedAt: Date.now(),
  }
  languageDictCache.set(safeLang, entry)
  return entry
}

export const hydrateMediaRecord = (
  record: RawMediaRecord,
  dicts: LanguageDictionaries,
  mediaBucket: string
): HydratedMediaItem => {
  const labels = record.label_indexes
    .map((idx) => dicts.labels[String(idx)])
    .filter((label): label is string => Boolean(label))
  const caption =
    record.caption_index !== null && record.caption_index !== undefined
      ? dicts.captions[String(record.caption_index)] || null
      : null

  return {
    hash: record.hash,
    averageHash: record.average_hash,
    fileType: record.file_type,
    createdAt: record.created_at,
    createdAtTimestamp: record.created_at_timestamp,
    latitude: record.latitude,
    longitude: record.longitude,
    geohash: record.geohash,
    labels,
    caption,
    proxyUrls: {
      sourceUrl: toProxyUrl(record.source_bucket_uri, mediaBucket) || '',
      thumbnailUrl: toProxyUrl(record.thumbnail_bucket_uri, mediaBucket),
    },
  }
}

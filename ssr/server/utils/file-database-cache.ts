import { createError } from 'h3'
import {
  formatUtcMonthDay,
  GEOHASH_PRECISIONS,
  LANG_REGEX,
  SHA1_REGEX,
  toEpochMilliseconds,
  UINT_KEY_REGEX,
  VALID_FILE_TYPES,
} from '#shared/index'
import type {
  GeohashClusterBucket,
  GeohashPrecision,
  KeyValueDictionary,
  LanguageDictionaries,
  MediaDatabaseSnapshot,
  RawMediaRecord,
} from '../types/cache'
import { createSingleFlight } from './async-mutex'
import { encodeGeohash, isValidCoordinatePair } from './geohash'
import { loadJsonDatabase, type StorageOptions } from './storage-download'

export { formatUtcMonthDay, toEpochMilliseconds }

let mediaDbCache: MediaDatabaseSnapshot | null = null
const languageDictCache = new Map<string, LanguageDictionaries>()
let cacheEpoch = 0
const dbSingleFlight = createSingleFlight<string, MediaDatabaseSnapshot>()
const dictSingleFlight = createSingleFlight<string, LanguageDictionaries>()

export const normalizeLanguageCode = (raw: unknown, fallback = 'en'): string => {
  if (typeof raw !== 'string') {
    return fallback
  }
  const clean = raw.trim().toLowerCase()
  return LANG_REGEX.test(clean) ? clean : fallback
}

export const invalidateFileDatabaseCache = (): void => {
  cacheEpoch += 1
  mediaDbCache = null
  languageDictCache.clear()
  dbSingleFlight.clear()
  dictSingleFlight.clear()
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
    if (typeof rec.file_type !== 'string' || !VALID_FILE_TYPES.has(rec.file_type as never)) {
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

export const buildDerivedMediaIndexes = (
  recordsByHash: Record<string, RawMediaRecord>,
  sortedHashes: string[]
): {
  byMonthDay: Record<string, string[]>
  byLabelIndex: Record<number, string[]>
  byCaptionIndex: Record<number, string[]>
  geolocatedHashes: string[]
  unfilteredGeohashBuckets: Record<GeohashPrecision, GeohashClusterBucket[]>
} => {
  const byMonthDay: Record<string, string[]> = {}
  const byLabelIndex: Record<number, string[]> = {}
  const byCaptionIndex: Record<number, string[]> = {}
  const geolocatedHashes: string[] = []
  const accumulators: Record<
    GeohashPrecision,
    Map<string, { count: number; sumLat: number; sumLng: number }>
  > = {
    2: new Map(),
    3: new Map(),
    4: new Map(),
    5: new Map(),
    6: new Map(),
  }

  for (const hash of sortedHashes) {
    const rec = recordsByHash[hash]
    if (!rec) continue

    if (typeof rec.created_at_timestamp === 'number' && Number.isFinite(rec.created_at_timestamp)) {
      const mmdd = formatUtcMonthDay(rec.created_at_timestamp)
      if (mmdd) {
        if (!byMonthDay[mmdd]) {
          byMonthDay[mmdd] = []
        }
        byMonthDay[mmdd].push(hash)
      }
    }

    for (const labelIndex of new Set(rec.label_indexes)) {
      if (!byLabelIndex[labelIndex]) {
        byLabelIndex[labelIndex] = []
      }
      byLabelIndex[labelIndex].push(hash)
    }

    if (typeof rec.caption_index === 'number' && Number.isInteger(rec.caption_index)) {
      if (!byCaptionIndex[rec.caption_index]) {
        byCaptionIndex[rec.caption_index] = []
      }
      byCaptionIndex[rec.caption_index]!.push(hash)
    }

    if (isValidCoordinatePair(rec.latitude, rec.longitude)) {
      const lat = rec.latitude as number
      const lng = rec.longitude as number
      geolocatedHashes.push(hash)

      const existingGeohash =
        typeof rec.geohash === 'string' ? rec.geohash.trim().toLowerCase() : ''
      const canonicalGeohash =
        existingGeohash.length >= 6 ? existingGeohash : encodeGeohash(lat, lng, 6)
      if (rec.geohash !== canonicalGeohash) {
        rec.geohash = canonicalGeohash
      }

      for (const precision of GEOHASH_PRECISIONS) {
        const prefix = canonicalGeohash.slice(0, precision)
        const map = accumulators[precision]
        const bucket = map.get(prefix)
        if (bucket) {
          bucket.count += 1
          bucket.sumLat += lat
          bucket.sumLng += lng
        } else {
          map.set(prefix, { count: 1, sumLat: lat, sumLng: lng })
        }
      }
    }
  }

  const unfilteredGeohashBuckets = {} as Record<GeohashPrecision, GeohashClusterBucket[]>
  for (const precision of GEOHASH_PRECISIONS) {
    const list: GeohashClusterBucket[] = []
    for (const [prefix, acc] of accumulators[precision].entries()) {
      list.push({
        prefix,
        count: acc.count,
        avgLat: acc.sumLat / acc.count,
        avgLng: acc.sumLng / acc.count,
      })
    }
    unfilteredGeohashBuckets[precision] = list
  }

  return { byMonthDay, byLabelIndex, byCaptionIndex, geolocatedHashes, unfilteredGeohashBuckets }
}

export const getMediaDatabase = async (
  idToken: string,
  options?: StorageOptions & { dbFileName?: string }
): Promise<MediaDatabaseSnapshot> => {
  if (mediaDbCache && !options?.forceRefresh) {
    return mediaDbCache
  }
  const dbFileName = options?.dbFileName || 'photosphere_database_cloud.json'
  const entryEpoch = cacheEpoch

  const loadSnapshot = async (): Promise<MediaDatabaseSnapshot> => {
    const recordsByHash = await loadJsonDatabase(
      dbFileName,
      dbFileName,
      idToken,
      validateMediaDatabasePayload,
      options
    )
    const sortedHashes = sortMediaHashesDescending(recordsByHash)
    const { byMonthDay, byLabelIndex, byCaptionIndex, geolocatedHashes, unfilteredGeohashBuckets } =
      buildDerivedMediaIndexes(recordsByHash, sortedHashes)
    const snapshot: MediaDatabaseSnapshot = {
      recordsByHash,
      sortedHashes,
      byMonthDay,
      byLabelIndex,
      byCaptionIndex,
      geolocatedHashes,
      unfilteredGeohashBuckets,
      loadedAt: Date.now(),
    }
    if (entryEpoch === cacheEpoch) {
      mediaDbCache = snapshot
    }
    return snapshot
  }

  if (options?.forceRefresh) {
    return await loadSnapshot()
  }

  return await dbSingleFlight.run(`${dbFileName}:${entryEpoch}`, loadSnapshot)
}

const loadSingleDictionaryWithFallback = async (
  lang: string,
  suffixFileName: string,
  idToken: string,
  options?: StorageOptions
): Promise<KeyValueDictionary> => {
  const safeLang = normalizeLanguageCode(lang, 'en')
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
  const safeLang = normalizeLanguageCode(lang, 'en')
  const cached = languageDictCache.get(safeLang)
  if (cached && !options?.forceRefresh) {
    return cached
  }

  const labelsSuffix = options?.labelsSuffix || 'photosphere_image_labelling_database_cloud.json'
  const captionsSuffix = options?.captionsSuffix || 'photosphere_image_caption_database_cloud.json'
  const entryEpoch = cacheEpoch

  const loadEntry = async (): Promise<LanguageDictionaries> => {
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
    if (entryEpoch === cacheEpoch) {
      languageDictCache.set(safeLang, entry)
    }
    return entry
  }

  if (options?.forceRefresh) {
    return await loadEntry()
  }

  return await dictSingleFlight.run(
    `${safeLang}:${labelsSuffix}:${captionsSuffix}:${entryEpoch}`,
    loadEntry
  )
}

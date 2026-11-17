import { defineEventHandler, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import type { HydratedMediaItem, MediaFileType } from '../../types/cache'
import { getAlbums } from '../../utils/albums-cache'
import {
  getLanguageDictionaries,
  getMediaDatabase,
  hydrateMediaRecord,
} from '../../utils/file-database-cache'
import {
  matchesMediaFilters,
  normalizeLanguageCode,
  parsePagination,
} from '../../utils/file-filters'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

export default defineEventHandler(async (event) => {
  const cfg = useRuntimeConfig(event)
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const query = getQuery(event)

  const lang = normalizeLanguageCode(query.lang, cfg.public?.defaultLang || 'en')
  const { page, limit } = parsePagination(query.page, query.limit)

  const albumName =
    typeof query.album === 'string' && query.album.trim() ? query.album.trim() : undefined
  const rawType = typeof query.fileType === 'string' ? query.fileType.toUpperCase() : 'ALL'
  const fileType: MediaFileType | 'ALL' =
    rawType === 'IMAGE' || rawType === 'VIDEO' || rawType === 'FILE' ? rawType : 'ALL'

  const dateFrom = query.dateFrom ? Number(query.dateFrom) : undefined
  const dateTo = query.dateTo ? Number(query.dateTo) : undefined
  const hasLocation = query.hasLocation === 'true' || query.hasLocation === '1'
  const searchQuery = typeof query.q === 'string' ? query.q : undefined

  const [snapshot, dicts, albums] = await Promise.all([
    getMediaDatabase(idToken, { ...storageOpts, dbFileName: cfg.database?.jsonFileName }),
    getLanguageDictionaries(lang, idToken, {
      ...storageOpts,
      labelsSuffix: cfg.database?.labelsJsonFileName,
      captionsSuffix: cfg.database?.captionsJsonFileName,
    }),
    albumName
      ? getAlbums(idToken, { ...storageOpts, albumsFileName: cfg.database?.albumsJsonFileName })
      : Promise.resolve([]),
  ])

  let albumHashes: Set<string> | undefined
  if (albumName) {
    const found = albums.find((a) => a.name === albumName)
    albumHashes = new Set(found ? found.hashes : [])
  }

  const mediaBucket = storageOpts.mediaBucket || ''
  const matched: HydratedMediaItem[] = []

  for (const hash of snapshot.sortedHashes) {
    const record = snapshot.recordsByHash[hash]
    if (!record) {
      continue
    }
    const hydrated = hydrateMediaRecord(record, dicts, mediaBucket)
    if (
      matchesMediaFilters(hydrated, {
        q: searchQuery,
        fileType,
        dateFrom: Number.isFinite(dateFrom) ? dateFrom : undefined,
        dateTo: Number.isFinite(dateTo) ? dateTo : undefined,
        hasLocation,
        albumHashes,
      })
    ) {
      matched.push(hydrated)
    }
  }

  const total = matched.length
  const totalPages = Math.max(1, Math.ceil(total / limit))
  const start = (page - 1) * limit
  const items = matched.slice(start, start + limit)

  return {
    items,
    total,
    page,
    limit,
    totalPages,
    lang: dicts.lang,
  }
})

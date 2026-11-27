import { createError, defineEventHandler, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import { normalizeLanguageCode } from '../../utils/file-database-cache'
import {
  filterMediaHashes,
  sortMediaHashesByDistance,
  toMediaGridItem,
} from '../../utils/file-filters'
import {
  getRuntimeDatabaseNames,
  loadFilterDependencies,
  parseMediaFilterQuery,
  parsePaginationParams,
} from '../../utils/request-parsers'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

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
  const dbNames = getRuntimeDatabaseNames(event)
  const query = getQuery(event)

  const { page, limit, skip } = parsePaginationParams(query, 50, 200)
  const sort = parseSortOrder(query.sort)
  const filters = parseMediaFilterQuery(query, { includeSpatial: true })
  const lang = normalizeLanguageCode(query.lang, cfg.public?.defaultLang || 'en')

  const { snapshot, dicts, albums } = await loadFilterDependencies(idToken, storageOpts, dbNames, {
    lang,
    needDicts: Boolean(filters.q),
    needAlbums: Boolean(filters.album || filters.notInAlbum),
  })

  const matchingHashes = filterMediaHashes(snapshot, filters, { dicts, albums })

  if (sort === 'distance' && filters.lat !== undefined && filters.lng !== undefined) {
    const distanceSorted = sortMediaHashesByDistance(
      snapshot,
      matchingHashes,
      filters.lat,
      filters.lng
    )
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

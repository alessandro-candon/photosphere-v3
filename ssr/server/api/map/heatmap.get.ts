import { createError, defineEventHandler, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import { normalizeLanguageCode } from '../../utils/file-database-cache'
import { aggregateViewportHeatmap, type HeatmapDataMode } from '../../utils/map-aggregation'
import {
  getRuntimeDatabaseNames,
  loadFilterDependencies,
  parseMediaFilterQuery,
  parseOptionalNumber,
} from '../../utils/request-parsers'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

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
  const dbNames = getRuntimeDatabaseNames(event)
  const query = getQuery(event)

  const north = parseOptionalNumber(query.north)
  const south = parseOptionalNumber(query.south)
  const east = parseOptionalNumber(query.east)
  const west = parseOptionalNumber(query.west)

  const parsedZoom = parseOptionalNumber(query.zoom)
  const zoom = parsedZoom !== undefined ? Math.min(Math.max(Math.round(parsedZoom), 2), 16) : 3
  const mode = parseDataMode(query.mode)
  const filters = parseMediaFilterQuery(query, { includeSpatial: false })
  const lang = normalizeLanguageCode(query.lang, cfg.public?.defaultLang || 'en')

  const { snapshot, dicts, albums } = await loadFilterDependencies(idToken, storageOpts, dbNames, {
    lang,
    needDicts: Boolean(filters.q),
    needAlbums: Boolean(filters.album || filters.notInAlbum),
  })

  return aggregateViewportHeatmap(
    snapshot,
    { north, south, east, west, zoom, mode, filters },
    { dicts, albums }
  )
})

import type {
  AlbumRecord,
  GeohashPrecision,
  LanguageDictionaries,
  MediaDatabaseSnapshot,
} from '../types/cache'
import { filterMediaHashes, type MediaFilterParams } from './file-filters'
import { encodeGeohash, resolveGeohashPrecision } from './geohash'

export const RAW_MODE_MAX_POINTS = 5000

export type HeatmapDataMode = 'geohash' | 'raw'
export type HeatmapPointTuple = [number, number, number]

export interface ViewportBounds {
  south: number
  north: number
  west: number
  east: number
  fullWorldLng: boolean
}

export interface HeatmapAggregationParams {
  north?: number
  south?: number
  east?: number
  west?: number
  zoom: number
  mode: HeatmapDataMode
  filters?: MediaFilterParams
}

export interface HeatmapApiResponse {
  points: HeatmapPointTuple[]
  precision: GeohashPrecision
  requestedMode: HeatmapDataMode
  effectiveMode: HeatmapDataMode
  fallbackTriggered: boolean
  viewportPointCount: number
  totalGeolocatedCount: number
  maxBucketCount: number
}

const clamp = (value: number, min: number, max: number): number =>
  Math.min(Math.max(value, min), max)

const wrapLongitude = (lng: number): number => ((((lng + 180) % 360) + 360) % 360) - 180

export const normalizeViewportBounds = (
  rawNorth?: number,
  rawSouth?: number,
  rawEast?: number,
  rawWest?: number
): ViewportBounds => {
  const northVal = typeof rawNorth === 'number' && Number.isFinite(rawNorth) ? rawNorth : 90
  const southVal = typeof rawSouth === 'number' && Number.isFinite(rawSouth) ? rawSouth : -90
  const south = clamp(Math.min(southVal, northVal), -90, 90)
  const north = clamp(Math.max(southVal, northVal), -90, 90)

  if (
    typeof rawEast !== 'number' ||
    !Number.isFinite(rawEast) ||
    typeof rawWest !== 'number' ||
    !Number.isFinite(rawWest) ||
    rawEast - rawWest >= 360
  ) {
    return { south, north, west: -180, east: 180, fullWorldLng: true }
  }

  return {
    south,
    north,
    west: wrapLongitude(rawWest),
    east: wrapLongitude(rawEast),
    fullWorldLng: false,
  }
}

export const isPointInViewport = (lat: number, lng: number, bounds: ViewportBounds): boolean => {
  if (lat < bounds.south || lat > bounds.north) {
    return false
  }
  if (bounds.fullWorldLng) {
    return true
  }
  if (bounds.west <= bounds.east) {
    return lng >= bounds.west && lng <= bounds.east
  }
  return lng >= bounds.west || lng <= bounds.east
}

export const hasActiveNonSpatialFilters = (filters?: MediaFilterParams): boolean => {
  if (!filters) return false
  return Boolean(
    (filters.q && filters.q.trim()) ||
    filters.labelIndex !== undefined ||
    filters.captionIndex !== undefined ||
    filters.fileType ||
    (filters.dateFrom && filters.dateFrom.trim()) ||
    (filters.dateTo && filters.dateTo.trim()) ||
    (filters.memoryDate && filters.memoryDate.trim()) ||
    (filters.album && filters.album.trim()) ||
    filters.notInAlbum
  )
}

const computeLogWeight = (count: number, maxBucketCount: number): number => {
  if (maxBucketCount <= 1) return 1.0
  const ratio = Math.log(count + 1) / Math.log(maxBucketCount + 1)
  return Number(clamp(ratio, 0.08, 1.0).toFixed(4))
}

export const aggregateViewportHeatmap = (
  snapshot: MediaDatabaseSnapshot,
  params: HeatmapAggregationParams,
  options: { dicts?: LanguageDictionaries; albums?: AlbumRecord[] } = {}
): HeatmapApiResponse => {
  const precision = resolveGeohashPrecision(params.zoom)
  const bounds = normalizeViewportBounds(params.north, params.south, params.east, params.west)
  const totalGeolocatedCount = snapshot.geolocatedHashes.length
  const requestedMode: HeatmapDataMode = params.mode === 'raw' ? 'raw' : 'geohash'
  const hasFilters = hasActiveNonSpatialFilters(params.filters)

  // Tier 1: Unfiltered O(B) fast path for geohash mode
  if (!hasFilters && requestedMode === 'geohash') {
    const precomputed = snapshot.unfilteredGeohashBuckets[precision] || []
    const matchedBuckets: Array<{ avgLat: number; avgLng: number; count: number }> = []
    let maxBucketCount = 0
    let viewportPointCount = 0

    for (const bucket of precomputed) {
      if (!isPointInViewport(bucket.avgLat, bucket.avgLng, bounds)) {
        continue
      }
      matchedBuckets.push(bucket)
      viewportPointCount += bucket.count
      if (bucket.count > maxBucketCount) {
        maxBucketCount = bucket.count
      }
    }

    const points: HeatmapPointTuple[] = matchedBuckets.map((bucket) => [
      Number(bucket.avgLat.toFixed(6)),
      Number(bucket.avgLng.toFixed(6)),
      computeLogWeight(bucket.count, maxBucketCount),
    ])

    return {
      points,
      precision,
      requestedMode,
      effectiveMode: 'geohash',
      fallbackTriggered: false,
      viewportPointCount,
      totalGeolocatedCount,
      maxBucketCount,
    }
  }

  // Tier 2: Filtered pass (or raw mode) restricted to geolocatedHashes
  const nonSpatialFilters: MediaFilterParams = params.filters
    ? {
        q: params.filters.q,
        searchField: params.filters.searchField,
        labelIndex: params.filters.labelIndex,
        captionIndex: params.filters.captionIndex,
        fileType: params.filters.fileType,
        dateFrom: params.filters.dateFrom,
        dateTo: params.filters.dateTo,
        memoryDate: params.filters.memoryDate,
        album: params.filters.album,
        notInAlbum: params.filters.notInAlbum,
      }
    : {}

  const candidateHashes = hasFilters
    ? filterMediaHashes(snapshot, nonSpatialFilters, {
        ...options,
        baseHashes: snapshot.geolocatedHashes,
      })
    : snapshot.geolocatedHashes

  const viewportHashes: string[] = []
  for (const hash of candidateHashes) {
    const rec = snapshot.recordsByHash[hash]
    if (!rec || rec.latitude === null || rec.longitude === null) continue
    if (isPointInViewport(rec.latitude, rec.longitude, bounds)) {
      viewportHashes.push(hash)
    }
  }

  const viewportPointCount = viewportHashes.length

  if (requestedMode === 'raw' && viewportPointCount <= RAW_MODE_MAX_POINTS) {
    const points: HeatmapPointTuple[] = []
    for (const hash of viewportHashes) {
      const rec = snapshot.recordsByHash[hash]
      if (!rec || rec.latitude === null || rec.longitude === null) continue
      points.push([Number(rec.latitude.toFixed(6)), Number(rec.longitude.toFixed(6)), 0.75])
    }
    return {
      points,
      precision,
      requestedMode,
      effectiveMode: 'raw',
      fallbackTriggered: false,
      viewportPointCount,
      totalGeolocatedCount,
      maxBucketCount: viewportPointCount > 0 ? 1 : 0,
    }
  }

  const fallbackTriggered = requestedMode === 'raw' && viewportPointCount > RAW_MODE_MAX_POINTS
  const buckets = new Map<string, { count: number; sumLat: number; sumLng: number }>()
  let maxBucketCount = 0

  for (const hash of viewportHashes) {
    const rec = snapshot.recordsByHash[hash]
    if (!rec || rec.latitude === null || rec.longitude === null) continue
    const gh =
      typeof rec.geohash === 'string' && rec.geohash.length >= precision
        ? rec.geohash
        : encodeGeohash(rec.latitude, rec.longitude, 6)
    const prefix = gh.slice(0, precision)
    const existing = buckets.get(prefix)
    if (existing) {
      existing.count += 1
      existing.sumLat += rec.latitude
      existing.sumLng += rec.longitude
      if (existing.count > maxBucketCount) {
        maxBucketCount = existing.count
      }
    } else {
      buckets.set(prefix, { count: 1, sumLat: rec.latitude, sumLng: rec.longitude })
      if (maxBucketCount < 1) {
        maxBucketCount = 1
      }
    }
  }

  const points: HeatmapPointTuple[] = []
  for (const bucket of buckets.values()) {
    points.push([
      Number((bucket.sumLat / bucket.count).toFixed(6)),
      Number((bucket.sumLng / bucket.count).toFixed(6)),
      computeLogWeight(bucket.count, maxBucketCount),
    ])
  }

  return {
    points,
    precision,
    requestedMode,
    effectiveMode: 'geohash',
    fallbackTriggered,
    viewportPointCount,
    totalGeolocatedCount,
    maxBucketCount,
  }
}

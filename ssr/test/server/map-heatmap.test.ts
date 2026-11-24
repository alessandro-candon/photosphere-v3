import { IncomingMessage, ServerResponse } from 'node:http'
import { mkdtempSync, rmSync } from 'node:fs'
import { Socket } from 'node:net'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { createEvent, type H3Event } from 'h3'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import filesListHandler from '../../server/api/files/index.get'
import heatmapHandler from '../../server/api/map/heatmap.get'
import type { MediaDatabaseSnapshot, RawMediaRecord } from '../../server/types/cache'
import { invalidateAlbumsCache } from '../../server/utils/albums-cache'
import {
  buildDerivedMediaIndexes,
  invalidateFileDatabaseCache,
  sortMediaHashesDescending,
} from '../../server/utils/file-database-cache'
import { encodeGeohash, resolveGeohashPrecision } from '../../server/utils/geohash'
import {
  aggregateViewportHeatmap,
  isPointInViewport,
  normalizeViewportBounds,
  RAW_MODE_MAX_POINTS,
} from '../../server/utils/map-aggregation'
import { setMockRuntimeConfig } from '../nuxt-imports-stub'

const makeHash = (idx: number): string => idx.toString(16).padStart(40, '0')

const makeRecord = (idx: number, overrides: Partial<RawMediaRecord> = {}): RawMediaRecord => {
  const hash = makeHash(idx)
  return {
    hash,
    average_hash: null,
    source_bucket_uri: `gs://test-media/photos/IMG_${idx}.jpg`,
    thumbnail_bucket_uri: `gs://test-media/thumbs/IMG_${idx}.jpg`,
    file_type: 'IMAGE',
    created_at: '2024-06-01T12:00:00Z',
    created_at_timestamp: 1717243200 + idx,
    latitude: 45.4642,
    longitude: 9.19,
    geohash: null,
    label_indexes: [0],
    caption_index: null,
    ...overrides,
  }
}

const makeSnapshot = (records: RawMediaRecord[]): MediaDatabaseSnapshot => {
  const recordsByHash: Record<string, RawMediaRecord> = {}
  for (const rec of records) {
    recordsByHash[rec.hash] = rec
  }
  const sortedHashes = sortMediaHashesDescending(recordsByHash)
  const indexes = buildDerivedMediaIndexes(recordsByHash, sortedHashes)
  return {
    recordsByHash,
    sortedHashes,
    ...indexes,
    loadedAt: Date.now(),
  }
}

const makeEvent = (path: string): H3Event => {
  const req = new IncomingMessage(new Socket())
  req.url = path
  req.method = 'GET'
  req.headers.authorization = 'Bearer tok-map'
  const res = new ServerResponse(req)
  const event = createEvent(req, res)
  event.context.auth = { uid: 'u1', email: 'user@example.com', email_verified: true }
  event.context.idToken = 'tok-map'
  return event
}

describe('Geohash, Viewport Bounds & Heatmap Aggregation', () => {
  it('encodes standard base32 geohashes and maps zoom levels to precisions 2..6', () => {
    expect(encodeGeohash(45.4642, 9.19, 6)).toBe('u0nd9h')
    expect(encodeGeohash(0, 0, 6)).toBe('s00000')

    expect(resolveGeohashPrecision(2)).toBe(2)
    expect(resolveGeohashPrecision(3)).toBe(2)
    expect(resolveGeohashPrecision(4)).toBe(3)
    expect(resolveGeohashPrecision(5)).toBe(3)
    expect(resolveGeohashPrecision(8)).toBe(4)
    expect(resolveGeohashPrecision(11)).toBe(5)
    expect(resolveGeohashPrecision(12)).toBe(6)
    expect(resolveGeohashPrecision(16)).toBe(6)
  })

  it('normalizes standard, full-world, and antimeridian-crossing viewport bounds', () => {
    const fullWorld = normalizeViewportBounds(95, -95, 220, -200)
    expect(fullWorld.fullWorldLng).toBe(true)
    expect(fullWorld.north).toBe(90)
    expect(fullWorld.south).toBe(-90)
    expect(isPointInViewport(35, 139, fullWorld)).toBe(true)

    const antimeridian = normalizeViewportBounds(50, -50, -170, 170)
    expect(antimeridian.fullWorldLng).toBe(false)
    expect(isPointInViewport(0, 175, antimeridian)).toBe(true)
    expect(isPointInViewport(0, -175, antimeridian)).toBe(true)
    expect(isPointInViewport(0, 0, antimeridian)).toBe(false)
  })

  it('backfills missing geohashes and builds precomputed buckets on snapshot load', () => {
    const records = [
      makeRecord(1, { latitude: 45.4642, longitude: 9.19, geohash: null }),
      makeRecord(2, { latitude: 45.465, longitude: 9.191, geohash: 'u0nd9h' }),
      makeRecord(3, { latitude: null, longitude: null, geohash: null }),
    ]
    const snapshot = makeSnapshot(records)

    expect(snapshot.geolocatedHashes).toHaveLength(2)
    expect(snapshot.recordsByHash[makeHash(1)]?.geohash).toBe('u0nd9h')
    expect(snapshot.unfilteredGeohashBuckets[6]).toHaveLength(1)
    expect(snapshot.unfilteredGeohashBuckets[6][0]?.count).toBe(2)
  })

  it('uses O(B) unfiltered fast path and single-pass filtered aggregation with log weights', () => {
    const records = [
      makeRecord(1, { latitude: 45.4642, longitude: 9.19, file_type: 'IMAGE' }),
      makeRecord(2, { latitude: 45.4643, longitude: 9.1901, file_type: 'IMAGE' }),
      makeRecord(3, { latitude: 48.8566, longitude: 2.3522, file_type: 'VIDEO' }),
    ]
    const snapshot = makeSnapshot(records)

    const unfiltered = aggregateViewportHeatmap(snapshot, {
      north: 60,
      south: 35,
      east: 20,
      west: -5,
      zoom: 6,
      mode: 'geohash',
    })
    expect(unfiltered.effectiveMode).toBe('geohash')
    expect(unfiltered.fallbackTriggered).toBe(false)
    expect(unfiltered.viewportPointCount).toBe(3)
    expect(unfiltered.points).toHaveLength(2)
    for (const [, , weight] of unfiltered.points) {
      expect(weight).toBeGreaterThanOrEqual(0.08)
      expect(weight).toBeLessThanOrEqual(1.0)
    }

    const filtered = aggregateViewportHeatmap(snapshot, {
      north: 60,
      south: 35,
      east: 20,
      west: -5,
      zoom: 6,
      mode: 'geohash',
      filters: { fileType: 'VIDEO' },
    })
    expect(filtered.viewportPointCount).toBe(1)
    expect(filtered.points).toHaveLength(1)
    expect(filtered.points[0]?.[2]).toBe(1.0)
  })

  it('automatically falls back from raw mode to geohash when viewport points exceed 5,000', () => {
    const records: RawMediaRecord[] = []
    const count = RAW_MODE_MAX_POINTS + 50
    for (let i = 0; i < count; i++) {
      records.push(
        makeRecord(i + 1, {
          latitude: 40 + (i % 100) * 0.05,
          longitude: 5 + Math.floor(i / 100) * 0.05,
        })
      )
    }
    const snapshot = makeSnapshot(records)

    const res = aggregateViewportHeatmap(snapshot, {
      north: 60,
      south: 30,
      east: 30,
      west: 0,
      zoom: 6,
      mode: 'raw',
    })
    expect(res.requestedMode).toBe('raw')
    expect(res.effectiveMode).toBe('geohash')
    expect(res.fallbackTriggered).toBe(true)
    expect(res.viewportPointCount).toBe(count)
    expect(res.points.length).toBeLessThan(count)
  })
})

describe('GET /api/map/heatmap and GET /api/files?sort=distance', () => {
  const tempDirs: string[] = []
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    invalidateFileDatabaseCache()
    invalidateAlbumsCache()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    invalidateFileDatabaseCache()
    invalidateAlbumsCache()
    for (const dir of tempDirs.splice(0)) {
      rmSync(dir, { recursive: true, force: true })
    }
  })

  const setupFixture = () => {
    const vol = mkdtempSync(resolve(tmpdir(), 'ps-map-'))
    tempDirs.push(vol)

    setMockRuntimeConfig({
      public: { defaultLang: 'en' },
      storage: {
        dataBucket: 'test-data-bucket',
        mediaBucket: 'test-media-bucket',
        mountedVolumePath: vol,
      },
      database: {
        jsonFileName: 'photosphere_database_cloud.json',
        labelsJsonFileName: 'photosphere_image_labelling_database_cloud.json',
        captionsJsonFileName: 'photosphere_image_caption_database_cloud.json',
        albumsJsonFileName: 'photosphere_albums.json',
      },
    })

    const db: Record<string, RawMediaRecord> = {
      [makeHash(1)]: makeRecord(1, {
        latitude: 45.4642,
        longitude: 9.19,
        created_at_timestamp: 1700000100,
      }),
      [makeHash(2)]: makeRecord(2, {
        latitude: 45.472,
        longitude: 9.195,
        created_at_timestamp: 1700000300,
      }),
      [makeHash(3)]: makeRecord(3, {
        latitude: 45.4645,
        longitude: 9.1902,
        created_at_timestamp: 1700000200,
      }),
    }

    globalThis.fetch = vi.fn(async () => {
      return new Response(JSON.stringify(db), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }) as typeof fetch
  }

  it('serves /api/map/heatmap and sorts /api/files by ascending distance with limit up to 200', async () => {
    setupFixture()

    const heatmapRes = await heatmapHandler(
      makeEvent('/api/map/heatmap?north=50&south=40&east=15&west=5&zoom=12&mode=raw')
    )
    expect(heatmapRes.effectiveMode).toBe('raw')
    expect(heatmapRes.points).toHaveLength(3)

    const filesRes = await filesListHandler(
      makeEvent('/api/files?lat=45.4642&lng=9.19&radiusKm=10&sort=distance&limit=200')
    )
    expect(filesRes.limit).toBe(200)
    expect(filesRes.items).toHaveLength(3)
    expect(filesRes.items[0]?.hash).toBe(makeHash(1))
    expect(filesRes.items[1]?.hash).toBe(makeHash(3))
    expect(filesRes.items[2]?.hash).toBe(makeHash(2))
    expect(filesRes.items[0]?.latitude).toBe(45.4642)
    expect(filesRes.items[0]?.distanceKm).toBe(0)
    expect((filesRes.items[1]?.distanceKm ?? 0) < (filesRes.items[2]?.distanceKm ?? 0)).toBe(true)
  })
})

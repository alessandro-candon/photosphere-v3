import { IncomingMessage, ServerResponse } from 'node:http'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { Socket } from 'node:net'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { createEvent, type H3Event } from 'h3'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import fileDetailHandler from '../../server/api/files/[hash].get'
import filesListHandler from '../../server/api/files/index.get'
import { invalidateAlbumsCache } from '../../server/utils/albums-cache'
import { invalidateFileDatabaseCache } from '../../server/utils/file-database-cache'
import { haversineDistanceKm } from '../../server/utils/file-filters'
import { setMockRuntimeConfig } from '../nuxt-imports-stub'

const CONTRACTS_FIXTURES_DIR = resolve(__dirname, '../../../contracts/fixtures')

const HASH_MILAN_IMG = 'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678'
const HASH_MILAN_OLDER_MEMORY = 'dddddddddddddddddddddddddddddddddddddddd'
const HASH_VIDEO_NO_GPS = '0123456789abcdef0123456789abcdef01234567'
const HASH_NULL_DATES_AND_COORDS = 'cccccccccccccccccccccccccccccccccccccccc'

const makeEvent = (path: string, params?: Record<string, string>): H3Event => {
  const req = new IncomingMessage(new Socket())
  req.url = path
  req.method = 'GET'
  req.headers.authorization = 'Bearer tok-files'
  const res = new ServerResponse(req)
  const event = createEvent(req, res)
  if (params) {
    event.context.params = params
  }
  event.context.auth = { uid: 'u1', email: 'user@example.com', email_verified: true }
  event.context.idToken = 'tok-files'
  return event
}

describe('GET /api/files, GET /api/files/[hash] & Filtering Indexes', () => {
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

  const setupFixtureEnv = () => {
    const vol = mkdtempSync(resolve(tmpdir(), 'ps-files-'))
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

    const baseDb = JSON.parse(
      readFileSync(resolve(CONTRACTS_FIXTURES_DIR, 'valid_media_db.json'), 'utf-8')
    ) as Record<string, Record<string, unknown>>

    // Add a nullable record (null timestamps, null thumbnail, null coords, null caption)
    baseDb[HASH_NULL_DATES_AND_COORDS] = {
      hash: HASH_NULL_DATES_AND_COORDS,
      average_hash: null,
      source_bucket_uri: 'gs://photosphere-test-archive/docs/scan_notes.pdf',
      thumbnail_bucket_uri: null,
      file_type: 'FILE',
      created_at: null,
      created_at_timestamp: null,
      latitude: null,
      longitude: null,
      geohash: null,
      label_indexes: [],
      caption_index: null,
    }

    // Add a second 05-09 photo from an earlier year (2022-05-09T10:00:00Z) for multi-year Memories
    baseDb[HASH_MILAN_OLDER_MEMORY] = {
      hash: HASH_MILAN_OLDER_MEMORY,
      average_hash: null,
      source_bucket_uri: 'gs://photosphere-test-archive/2022/05/09/IMG_20220509.jpg',
      thumbnail_bucket_uri: null,
      file_type: 'IMAGE',
      created_at: '2022-05-09T10:00:00',
      created_at_timestamp: 1652090400,
      latitude: null,
      longitude: null,
      geohash: null,
      label_indexes: [0],
      caption_index: null,
    }

    const validLabelsRaw = readFileSync(
      resolve(CONTRACTS_FIXTURES_DIR, 'valid_en_labels.json'),
      'utf-8'
    )
    const validCaptionsRaw = readFileSync(
      resolve(CONTRACTS_FIXTURES_DIR, 'valid_en_captions.json'),
      'utf-8'
    )
    const validAlbumsRaw = readFileSync(
      resolve(CONTRACTS_FIXTURES_DIR, 'valid_albums.json'),
      'utf-8'
    )

    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const target = String(url)
      if (target.includes('labelling')) return new Response(validLabelsRaw, { status: 200 })
      if (target.includes('caption')) return new Response(validCaptionsRaw, { status: 200 })
      if (target.includes('albums')) return new Response(validAlbumsRaw, { status: 200 })
      return new Response(JSON.stringify(baseDb), { status: 200 })
    }) as unknown as typeof fetch
  }

  it('paginates newest-first and handles nullable MediaRecord fields cleanly', async () => {
    setupFixtureEnv()

    const page1 = await filesListHandler(makeEvent('/api/files?page=1&limit=2'))
    expect(page1.totalCount).toBe(4)
    expect(page1.hasMore).toBe(true)
    expect(page1.items.map((i) => i.hash)).toEqual([HASH_VIDEO_NO_GPS, HASH_MILAN_IMG])

    const page2 = await filesListHandler(makeEvent('/api/files?page=2&limit=2'))
    expect(page2.hasMore).toBe(false)
    expect(page2.items).toHaveLength(2)
    expect(page2.items[0]?.hash).toBe(HASH_MILAN_OLDER_MEMORY)
    expect(page2.items[1]).toMatchObject({
      hash: HASH_NULL_DATES_AND_COORDS,
      fileType: 'FILE',
      hasThumbnail: false,
      thumbnailUrl: null,
    })
  })

  it('filters by fileType, date range, search q, memoryDate, album, notInAlbum, and Haversine geo (excluding nulls)', async () => {
    setupFixtureEnv()

    const videosOnly = await filesListHandler(makeEvent('/api/files?fileType=VIDEO'))
    expect(videosOnly.items.map((i) => i.hash)).toEqual([HASH_VIDEO_NO_GPS])

    // Search matches caption/label text and filename
    const dogSearch = await filesListHandler(makeEvent('/api/files?q=golden%20dog&lang=en'))
    expect(dogSearch.items.map((i) => i.hash)).toEqual([HASH_MILAN_IMG])

    const filenameSearch = await filesListHandler(makeEvent('/api/files?q=scan_notes'))
    expect(filenameSearch.items.map((i) => i.hash)).toEqual([HASH_NULL_DATES_AND_COORDS])

    // Scoped searchField: labels vs captions
    const scopedLabelsDog = await filesListHandler(
      makeEvent('/api/files?q=dog&searchField=labels&lang=en')
    )
    expect(scopedLabelsDog.items.map((i) => i.hash)).toEqual([
      HASH_MILAN_IMG,
      HASH_MILAN_OLDER_MEMORY,
    ])

    const scopedLabelsCaptionWord = await filesListHandler(
      makeEvent('/api/files?q=sunlit&searchField=labels&lang=en')
    )
    expect(scopedLabelsCaptionWord.items).toEqual([])

    const scopedCaptionsSunlit = await filesListHandler(
      makeEvent('/api/files?q=sunlit&searchField=captions&lang=en')
    )
    expect(scopedCaptionsSunlit.items.map((i) => i.hash)).toEqual([HASH_MILAN_IMG])

    const scopedCaptionsDog = await filesListHandler(
      makeEvent('/api/files?q=dog&searchField=captions&lang=en')
    )
    expect(scopedCaptionsDog.items.map((i) => i.hash)).toEqual([HASH_MILAN_IMG])

    // Exact dictionary index filters
    const byLabelIndex = await filesListHandler(makeEvent('/api/files?labelIndex=1'))
    expect(byLabelIndex.items.map((i) => i.hash)).toEqual([HASH_MILAN_IMG])

    const byCaptionIndex = await filesListHandler(makeEvent('/api/files?captionIndex=1'))
    expect(byCaptionIndex.items.map((i) => i.hash)).toEqual([HASH_VIDEO_NO_GPS])

    await expect(
      filesListHandler(makeEvent('/api/files?searchField=unknown'))
    ).rejects.toMatchObject({ statusCode: 400 })

    // Date filter excludes null timestamp records
    const dated = await filesListHandler(
      makeEvent('/api/files?dateFrom=2024-01-01&dateTo=2024-12-31')
    )
    expect(dated.items.map((i) => i.hash)).toEqual([HASH_VIDEO_NO_GPS, HASH_MILAN_IMG])

    // Memories MM-DD lookup (05-09) returns multiple years newest-first and excludes null timestamps
    const memories = await filesListHandler(makeEvent('/api/files?memoryDate=05-09'))
    expect(memories.items.map((i) => i.hash)).toEqual([HASH_MILAN_IMG, HASH_MILAN_OLDER_MEMORY])

    // Location filter near Milan (45.4642, 9.19) matches Milan image ONLY — NEVER null coordinates
    expect(haversineDistanceKm(45.4642, 9.19, 45.4642, 9.19)).toBeCloseTo(0)
    const milanGeo = await filesListHandler(makeEvent('/api/files?lat=45.465&lng=9.191&radiusKm=5'))
    expect(milanGeo.items.map((i) => i.hash)).toEqual([HASH_MILAN_IMG])

    // Server-side album & notInAlbum filtering
    const inMilanAlbum = await filesListHandler(makeEvent('/api/files?album=Milan%202024'))
    expect(inMilanAlbum.items.map((i) => i.hash)).toEqual([HASH_VIDEO_NO_GPS, HASH_MILAN_IMG])

    const notInAnyAlbum = await filesListHandler(makeEvent('/api/files?notInAlbum=true'))
    expect(notInAnyAlbum.items.map((i) => i.hash)).toEqual([
      HASH_MILAN_OLDER_MEMORY,
      HASH_NULL_DATES_AND_COORDS,
    ])
  })

  it('returns detailed metadata with resolved localized labels/caption and 404 for unknown hash', async () => {
    setupFixtureEnv()

    const detail = await fileDetailHandler(
      makeEvent(`/api/files/${HASH_MILAN_IMG}?lang=en`, { hash: HASH_MILAN_IMG })
    )
    expect(detail.hash).toBe(HASH_MILAN_IMG)
    expect(detail.labels).toEqual(['dog', 'park'])
    expect(detail.caption).toContain('golden dog')

    await expect(
      fileDetailHandler(makeEvent(`/api/files/${'f'.repeat(40)}`, { hash: 'f'.repeat(40) }))
    ).rejects.toMatchObject({ statusCode: 404 })
  })
})

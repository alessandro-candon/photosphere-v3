import { IncomingMessage, ServerResponse } from 'node:http'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { Socket } from 'node:net'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { createEvent, type H3Event } from 'h3'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import mediaHandler from '../../server/api/media/[hash].get'
import {
  parseByteRange,
  resetMediaLruCacheForTests,
} from '../../server/services/media-cache.service'
import { invalidateFileDatabaseCache } from '../../server/utils/file-database-cache'
import { setMockRuntimeConfig } from '../nuxt-imports-stub'

const HASH_IMAGE = 'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678'
const HASH_VIDEO = '0123456789abcdef0123456789abcdef01234567'
const HASH_NO_THUMB_IMG = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
const HASH_NO_THUMB_VID = 'cccccccccccccccccccccccccccccccccccccccc'

const makeMediaEvent = (
  hash: string,
  query = '',
  headers: Record<string, string> = {}
): H3Event => {
  const req = new IncomingMessage(new Socket())
  req.url = `/api/media/${hash}${query ? `?${query}` : ''}`
  req.method = 'GET'
  for (const [k, v] of Object.entries(headers)) {
    req.headers[k.toLowerCase()] = v
  }
  const res = new ServerResponse(req)
  const event = createEvent(req, res)
  event.context.params = { hash }
  event.context.auth = { uid: 'u1', email: 'user@example.com', email_verified: true }
  event.context.idToken = 'tok-media'
  return event
}

describe('GET /api/media/[hash] Proxy & Bounded LRU Cache', () => {
  const tempDirs: string[] = []
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    resetMediaLruCacheForTests()
    invalidateFileDatabaseCache()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    resetMediaLruCacheForTests()
    invalidateFileDatabaseCache()
    for (const dir of tempDirs.splice(0)) {
      rmSync(dir, { recursive: true, force: true })
    }
  })

  it('rejects malformed hashes, invalid variants, and missing thumbnails on VIDEO', async () => {
    const vol = mkdtempSync(resolve(tmpdir(), 'ps-media-err-'))
    tempDirs.push(vol)

    setMockRuntimeConfig({
      storage: {
        dataBucket: 'data-bkt',
        mediaBucket: 'media-bkt',
        mountedVolumePath: vol,
      },
      mediaCache: { directoryName: 'media', maxCacheBytes: 1024, maxCacheableVideoBytes: 512 },
    })

    const dbPayload = {
      [HASH_NO_THUMB_VID]: {
        hash: HASH_NO_THUMB_VID,
        average_hash: null,
        source_bucket_uri: 'gs://media-bkt/clip.mp4',
        thumbnail_bucket_uri: null,
        file_type: 'VIDEO',
        created_at: null,
        created_at_timestamp: null,
        latitude: null,
        longitude: null,
        geohash: null,
        label_indexes: [],
        caption_index: null,
      },
    }

    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify(dbPayload), { status: 200 })
    ) as unknown as typeof fetch

    await expect(mediaHandler(makeMediaEvent('not-a-sha1'))).rejects.toMatchObject({
      statusCode: 400,
    })
    await expect(
      mediaHandler(makeMediaEvent(HASH_NO_THUMB_VID, 'variant=bad'))
    ).rejects.toMatchObject({ statusCode: 400 })
    await expect(mediaHandler(makeMediaEvent('f'.repeat(40)))).rejects.toMatchObject({
      statusCode: 404,
    })
    await expect(
      mediaHandler(makeMediaEvent(HASH_NO_THUMB_VID, 'variant=thumbnail'))
    ).rejects.toMatchObject({ statusCode: 404 })
  })

  it('caches media on disk, sets immutable/ETag headers, supports 304 and 206 Range, and falls back for null IMAGE thumbnail', async () => {
    const vol = mkdtempSync(resolve(tmpdir(), 'ps-media-hit-'))
    tempDirs.push(vol)

    setMockRuntimeConfig({
      storage: {
        dataBucket: 'data-bkt',
        mediaBucket: 'media-bkt',
        mountedVolumePath: vol,
      },
      mediaCache: {
        directoryName: 'media',
        maxCacheBytes: 1024 * 1024,
        maxCacheableVideoBytes: 1024,
      },
    })

    const dbPayload = {
      [HASH_IMAGE]: {
        hash: HASH_IMAGE,
        average_hash: null,
        source_bucket_uri: 'gs://media-bkt/photo.jpg',
        thumbnail_bucket_uri: 'gs://media-bkt/thumbs/photo.jpg',
        file_type: 'IMAGE',
        created_at: null,
        created_at_timestamp: 1000,
        latitude: null,
        longitude: null,
        geohash: null,
        label_indexes: [],
        caption_index: null,
      },
      [HASH_VIDEO]: {
        hash: HASH_VIDEO,
        average_hash: null,
        source_bucket_uri: 'gs://media-bkt/video.mp4',
        thumbnail_bucket_uri: 'gs://media-bkt/thumbs/video.jpg',
        file_type: 'VIDEO',
        created_at: null,
        created_at_timestamp: 2000,
        latitude: null,
        longitude: null,
        geohash: null,
        label_indexes: [],
        caption_index: null,
      },
      [HASH_NO_THUMB_IMG]: {
        hash: HASH_NO_THUMB_IMG,
        average_hash: null,
        source_bucket_uri: 'gs://media-bkt/raw.png',
        thumbnail_bucket_uri: null,
        file_type: 'IMAGE',
        created_at: null,
        created_at_timestamp: 3000,
        latitude: null,
        longitude: null,
        geohash: null,
        label_indexes: [],
        caption_index: null,
      },
    }

    let mediaFetchCount = 0
    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const target = String(url)
      if (target.includes('photosphere_database_cloud.json')) {
        return new Response(JSON.stringify(dbPayload), { status: 200 })
      }
      mediaFetchCount += 1
      if (target.includes('video.mp4')) {
        return new Response(new Uint8Array([10, 11, 12, 13, 14, 15, 16, 17]), {
          status: 200,
          headers: { 'content-type': 'video/mp4' },
        })
      }
      return new Response(new Uint8Array([1, 2, 3, 4]), {
        status: 200,
        headers: { 'content-type': 'image/jpeg' },
      })
    }) as unknown as typeof fetch

    // 1. Cold miss fetches from GCS
    const ev1 = makeMediaEvent(HASH_IMAGE, 'variant=thumbnail')
    const res1 = await mediaHandler(ev1)
    expect(Array.from(res1 as Uint8Array)).toEqual([1, 2, 3, 4])
    expect(mediaFetchCount).toBe(1)
    expect(ev1.node.res.getHeader('cache-control')).toBe('private, max-age=31536000, immutable')
    expect(ev1.node.res.getHeader('etag')).toBe(`"${HASH_IMAGE}-thumbnail"`)

    // 2. Warm disk cache hit does not call fetch
    const ev2 = makeMediaEvent(HASH_IMAGE, 'variant=thumbnail')
    const res2 = await mediaHandler(ev2)
    expect(Array.from(res2 as Uint8Array)).toEqual([1, 2, 3, 4])
    expect(mediaFetchCount).toBe(1)

    // 3. ETag 304 Not Modified
    const ev3 = makeMediaEvent(HASH_IMAGE, 'variant=thumbnail', {
      'if-none-match': `"${HASH_IMAGE}-thumbnail"`,
    })
    const res3 = await mediaHandler(ev3)
    expect(res3).toBeNull()
    expect(ev3.node.res.statusCode).toBe(304)

    // 4. Null thumbnail on IMAGE falls back to source_bucket_uri
    const evImgFallback = makeMediaEvent(HASH_NO_THUMB_IMG, 'variant=thumbnail')
    await mediaHandler(evImgFallback)
    expect(mediaFetchCount).toBe(2)

    // 5. Video download caches full object and subsequent Range request serves 206 locally
    const evVid1 = makeMediaEvent(HASH_VIDEO, 'variant=source')
    await mediaHandler(evVid1)
    expect(mediaFetchCount).toBe(3)

    const evVidRange = makeMediaEvent(HASH_VIDEO, 'variant=source', { range: 'bytes=2-5' })
    const resRange = await mediaHandler(evVidRange)
    expect(mediaFetchCount).toBe(3)
    expect(evVidRange.node.res.statusCode).toBe(206)
    expect(evVidRange.node.res.getHeader('content-range')).toBe('bytes 2-5/8')
    expect(Array.from(resRange as Uint8Array)).toEqual([12, 13, 14, 15])
  })

  it('evicts least-recently-used entries when maxCacheBytes is exceeded', async () => {
    const vol = mkdtempSync(resolve(tmpdir(), 'ps-media-lru-'))
    tempDirs.push(vol)

    setMockRuntimeConfig({
      storage: {
        dataBucket: 'data-bkt',
        mediaBucket: 'media-bkt',
        mountedVolumePath: vol,
      },
      // Fit at most two 4-byte entries (8 bytes total)
      mediaCache: { directoryName: 'media', maxCacheBytes: 8, maxCacheableVideoBytes: 8 },
    })

    const h1 = '1'.repeat(40)
    const h2 = '2'.repeat(40)
    const h3 = '3'.repeat(40)
    const dbPayload = {
      [h1]: {
        hash: h1,
        average_hash: null,
        source_bucket_uri: 'gs://media-bkt/1.jpg',
        thumbnail_bucket_uri: 'gs://media-bkt/t1.jpg',
        file_type: 'IMAGE',
        created_at: null,
        created_at_timestamp: 100,
        latitude: null,
        longitude: null,
        geohash: null,
        label_indexes: [],
        caption_index: null,
      },
      [h2]: {
        hash: h2,
        average_hash: null,
        source_bucket_uri: 'gs://media-bkt/2.jpg',
        thumbnail_bucket_uri: 'gs://media-bkt/t2.jpg',
        file_type: 'IMAGE',
        created_at: null,
        created_at_timestamp: 200,
        latitude: null,
        longitude: null,
        geohash: null,
        label_indexes: [],
        caption_index: null,
      },
      [h3]: {
        hash: h3,
        average_hash: null,
        source_bucket_uri: 'gs://media-bkt/3.jpg',
        thumbnail_bucket_uri: 'gs://media-bkt/t3.jpg',
        file_type: 'IMAGE',
        created_at: null,
        created_at_timestamp: 300,
        latitude: null,
        longitude: null,
        geohash: null,
        label_indexes: [],
        caption_index: null,
      },
    }

    let gcsCalls = 0
    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const target = String(url)
      if (target.includes('photosphere_database_cloud.json')) {
        return new Response(JSON.stringify(dbPayload), { status: 200 })
      }
      gcsCalls += 1
      return new Response(new Uint8Array([1, 2, 3, 4]), { status: 200 })
    }) as unknown as typeof fetch

    // Cache h1 then h2 (order: h1, h2)
    await mediaHandler(makeMediaEvent(h1, 'variant=thumbnail'))
    await mediaHandler(makeMediaEvent(h2, 'variant=thumbnail'))
    expect(gcsCalls).toBe(2)

    // Touch h1 so h2 becomes LRU (order: h2, h1)
    await mediaHandler(makeMediaEvent(h1, 'variant=thumbnail'))
    expect(gcsCalls).toBe(2)

    // Insert h3 -> evicts h2
    await mediaHandler(makeMediaEvent(h3, 'variant=thumbnail'))
    expect(gcsCalls).toBe(3)

    // h1 is still cached; h2 must re-fetch from GCS
    await mediaHandler(makeMediaEvent(h1, 'variant=thumbnail'))
    expect(gcsCalls).toBe(3)
    await mediaHandler(makeMediaEvent(h2, 'variant=thumbnail'))
    expect(gcsCalls).toBe(4)

    // Sanity check disk file exists for h2
    expect(readFileSync(resolve(vol, 'media', `${h2}.thumbnail.bin`)).byteLength).toBe(4)
  })

  it('rejects 0-byte suffix ranges with 416 and recovers cleanly from ENOENT on evicted cache files', async () => {
    expect(parseByteRange('bytes=-10', 0)).toBeNull()
    expect(parseByteRange('bytes=0-0', 0)).toBeNull()

    const vol = mkdtempSync(resolve(tmpdir(), 'ps-media-enoent-'))
    tempDirs.push(vol)
    setMockRuntimeConfig({
      storage: { dataBucket: 'data-bkt', mediaBucket: 'media-bkt', mountedVolumePath: vol },
      mediaCache: { directoryName: 'media', maxCacheBytes: 1024, maxCacheableVideoBytes: 1024 },
    })

    const dbPayload = {
      [HASH_IMAGE]: {
        hash: HASH_IMAGE,
        average_hash: null,
        source_bucket_uri: 'gs://media-bkt/photo.jpg',
        thumbnail_bucket_uri: 'gs://media-bkt/thumbs/photo.jpg',
        file_type: 'IMAGE',
        created_at: null,
        created_at_timestamp: 1000,
        latitude: null,
        longitude: null,
        geohash: null,
        label_indexes: [],
        caption_index: null,
      },
    }

    let mediaFetchCount = 0
    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      if (String(url).includes('photosphere_database_cloud.json')) {
        return new Response(JSON.stringify(dbPayload), { status: 200 })
      }
      mediaFetchCount += 1
      return new Response(new Uint8Array([7, 8, 9]), {
        status: 200,
        headers: { 'content-type': 'image/jpeg' },
      })
    }) as unknown as typeof fetch

    await mediaHandler(makeMediaEvent(HASH_IMAGE, 'variant=thumbnail'))
    expect(mediaFetchCount).toBe(1)

    // Unsatisfiable range on cached file -> 416
    await expect(
      mediaHandler(makeMediaEvent(HASH_IMAGE, 'variant=thumbnail', { range: 'bytes=99-120' }))
    ).rejects.toMatchObject({ statusCode: 416 })

    // Simulate external file deletion -> ENOENT falls back to upstream fetch
    rmSync(resolve(vol, 'media', `${HASH_IMAGE}.thumbnail.bin`), { force: true })
    const recovered = await mediaHandler(makeMediaEvent(HASH_IMAGE, 'variant=thumbnail'))
    expect(mediaFetchCount).toBe(2)
    expect(Array.from(recovered as Uint8Array)).toEqual([7, 8, 9])
  })
})

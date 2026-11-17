import { existsSync, mkdtempSync, readdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  parseByteRange,
  resolveBucketTier,
  serveCachedMediaObject,
  type MediaCacheConfigs,
} from '../../server/services/media-cache.service'
import {
  downloadDataFile,
  fetchMediaObject,
  uploadDataFile,
} from '../../server/utils/storage-download'

const readStreamText = async (
  stream: ReadableStream<Uint8Array> | NodeJS.ReadableStream
): Promise<string> => {
  if ('getReader' in stream) {
    const reader = stream.getReader()
    const chunks: Uint8Array[] = []
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      if (value) chunks.push(value)
    }
    return Buffer.concat(chunks).toString('utf-8')
  }
  const chunks: Buffer[] = []
  for await (const chunk of stream) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk))
  }
  return Buffer.concat(chunks).toString('utf-8')
}

describe('Dual-Bucket Storage Routing & Isolated Disk Caches', () => {
  const tempDirs: string[] = []

  afterEach(() => {
    for (const dir of tempDirs.splice(0)) {
      rmSync(dir, { recursive: true, force: true })
    }
  })

  const makeCacheConfigs = (vol: string, maxCacheBytes = 1024 * 1024): MediaCacheConfigs => ({
    mediaBucket: 'archive-media-bkt',
    mountedVolumePath: vol,
    thumbnailCache: {
      directoryName: 'thumbnail-cache',
      ttlMs: 60_000,
      maxObjectBytes: 4096,
      maxCacheBytes,
    },
    mediaCache: {
      directoryName: 'media-cache',
      ttlMs: 60_000,
      maxObjectBytes: 4096,
      maxCacheBytes,
    },
  })

  it('routes JSON downloads/uploads to dataBucket and enforces mediaBucket ownership', async () => {
    const fetchMock = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      expect(init?.headers).toMatchObject({ Authorization: 'Bearer id-tok' })
      if (String(url).includes('uploadType=media')) {
        return new Response('{}', { status: 200 })
      }
      return new Response('{"0":"cat"}', { status: 200 })
    }) as unknown as typeof fetch

    const downloaded = await downloadDataFile('en_labels.json', 'id-tok', {
      dataBucket: 'std-data-bkt',
      fetchImpl: fetchMock,
    })
    expect(downloaded).toBe('{"0":"cat"}')
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/b/std-data-bkt/o/en_labels.json'),
      expect.any(Object)
    )

    await uploadDataFile('photosphere_albums.json', '[]', 'id-tok', {
      dataBucket: 'std-data-bkt',
      fetchImpl: fetchMock,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/b/std-data-bkt/o?uploadType=media&name=photosphere_albums.json'),
      expect.objectContaining({ method: 'POST' })
    )

    await expect(
      fetchMediaObject('gs://wrong-bucket/photo.jpg', 'id-tok', {
        mediaBucket: 'archive-media-bkt',
        fetchImpl: fetchMock,
      })
    ).rejects.toMatchObject({ statusCode: 403 })
  })

  it('isolates thumbnail-cache from media-cache and serves Range 206 hits without upstream calls', async () => {
    const vol = mkdtempSync(resolve(tmpdir(), 'ps-cache-'))
    tempDirs.push(vol)
    const configs = makeCacheConfigs(vol, 32)

    expect(resolveBucketTier('thumbnails/2025/a.jpg')).toBe('thumbnail')
    expect(resolveBucketTier('2025/a.jpg')).toBe('media')
    expect(parseByteRange('bytes=2-5', 10)).toEqual({ start: 2, end: 5 })
    expect(parseByteRange('bytes=100-200', 10)).toBeNull()

    const fetchMock = vi.fn(async (url: string | URL | Request) => {
      const s = String(url)
      if (s.includes('thumbnails')) {
        return new Response('THUMB-BYTES-0123456789', {
          status: 200,
          headers: { 'content-type': 'image/jpeg' },
        })
      }
      return new Response('ORIG-MEDIA-PAYLOAD-0123456789', {
        status: 200,
        headers: { 'content-type': 'video/mp4' },
      })
    }) as unknown as typeof fetch

    const thumbMiss = await serveCachedMediaObject('thumbnails/2025/a.jpg', 'tok', configs, {
      fetchImpl: fetchMock,
    })
    expect(thumbMiss.bucketTier).toBe('thumbnail')
    expect(thumbMiss.cacheStatus).toBe('miss')
    expect(await readStreamText(thumbMiss.stream)).toBe('THUMB-BYTES-0123456789')

    const thumbHitRange = await serveCachedMediaObject('thumbnails/2025/a.jpg', 'tok', configs, {
      fetchImpl: fetchMock,
      rangeHeader: 'bytes=0-4',
    })
    expect(thumbHitRange.cacheStatus).toBe('hit')
    expect(thumbHitRange.statusCode).toBe(206)
    expect(thumbHitRange.contentRange).toBe('bytes 0-4/22')
    expect(await readStreamText(thumbHitRange.stream)).toBe('THUMB')
    expect(fetchMock).toHaveBeenCalledTimes(1)

    const mediaMiss = await serveCachedMediaObject('2025/a.mp4', 'tok', configs, {
      fetchImpl: fetchMock,
    })
    expect(mediaMiss.bucketTier).toBe('media')
    expect(await readStreamText(mediaMiss.stream)).toBe('ORIG-MEDIA-PAYLOAD-0123456789')

    // Populate two entries in media-cache exceeding maxCacheBytes=32; thumbnail-cache remains intact
    await serveCachedMediaObject('2025/b.mp4', 'tok', configs, { fetchImpl: fetchMock })
    expect(existsSync(join(vol, 'thumbnail-cache'))).toBe(true)
    expect(existsSync(join(vol, 'media-cache'))).toBe(true)
    const thumbFiles = readdirSync(join(vol, 'thumbnail-cache')).filter((f) => f.endsWith('.bin'))
    expect(thumbFiles).toHaveLength(1)

    // Suffix byte range on cached thumbnail
    const suffixHit = await serveCachedMediaObject('thumbnails/2025/a.jpg', 'tok', configs, {
      fetchImpl: fetchMock,
      rangeHeader: 'bytes=-4',
    })
    expect(suffixHit.statusCode).toBe(206)
    expect(await readStreamText(suffixHit.stream)).toBe('6789')

    // Invalid range returns 416 and traversal path returns 400
    await expect(
      serveCachedMediaObject('thumbnails/2025/a.jpg', 'tok', configs, {
        fetchImpl: fetchMock,
        rangeHeader: 'bytes=999-1000',
      })
    ).rejects.toMatchObject({ statusCode: 416 })
    await expect(serveCachedMediaObject('../secret.jpg', 'tok', configs)).rejects.toMatchObject({
      statusCode: 400,
    })

    // Upstream 206 partial video bypasses cache write without polling
    const rangeBypassFetch = vi.fn(
      async () =>
        new Response('PARTIAL', {
          status: 206,
          headers: {
            'content-type': 'video/mp4',
            'content-range': 'bytes 0-6/100',
          },
        })
    ) as unknown as typeof fetch
    const bypass = await serveCachedMediaObject('2025/uncached.mp4', 'tok', configs, {
      fetchImpl: rangeBypassFetch,
      rangeHeader: 'bytes=0-6',
    })
    expect(bypass.cacheStatus).toBe('bypass')
    expect(bypass.statusCode).toBe(206)
    expect(await readStreamText(bypass.stream)).toBe('PARTIAL')
  })

  it('handles storage misconfiguration, emulator URLs, and corrupted disk cache errors cleanly', async () => {
    await expect(
      downloadDataFile('db.json', 'tok', {
        dataBucket: '',
        fetchImpl: vi.fn() as unknown as typeof fetch,
      })
    ).rejects.toMatchObject({ statusCode: 500 })

    await expect(
      uploadDataFile('db.json', '{}', 'tok', {
        dataBucket: '',
        fetchImpl: vi.fn() as unknown as typeof fetch,
      })
    ).rejects.toMatchObject({ statusCode: 500 })

    await expect(
      fetchMediaObject('invalid-uri', 'tok', { mediaBucket: 'archive-bkt' })
    ).rejects.toMatchObject({ statusCode: 400 })

    const errFetch = vi.fn(
      async () => new Response('fail', { status: 500 })
    ) as unknown as typeof fetch
    await expect(
      fetchMediaObject('gs://archive-bkt/a.jpg', 'tok', {
        mediaBucket: 'archive-bkt',
        fetchImpl: errFetch,
      })
    ).rejects.toMatchObject({ statusCode: 502 })

    await expect(
      uploadDataFile('db.json', '{}', 'tok', { dataBucket: 'data-bkt', fetchImpl: errFetch })
    ).rejects.toMatchObject({ statusCode: 502 })

    process.env.STORAGE_EMULATOR_HOST = 'http://127.0.0.1:4443/'
    try {
      const emuFetch = vi.fn(
        async () => new Response('ok', { status: 200 })
      ) as unknown as typeof fetch
      await downloadDataFile('db.json', 'tok', { dataBucket: 'data-bkt', fetchImpl: emuFetch })
      expect(emuFetch).toHaveBeenCalledWith(
        expect.stringContaining('http://127.0.0.1:4443/storage/v1/b/data-bkt/o/db.json'),
        expect.any(Object)
      )
    } finally {
      delete process.env.STORAGE_EMULATOR_HOST
    }
  })
})

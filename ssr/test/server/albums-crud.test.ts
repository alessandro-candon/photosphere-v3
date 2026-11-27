import { IncomingMessage, ServerResponse } from 'node:http'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { Socket } from 'node:net'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { createEvent, type H3Event } from 'h3'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import albumDeleteHandler from '../../server/api/albums/[albumName].delete'
import albumGetHandler from '../../server/api/albums/[albumName].get'
import albumPatchHandler from '../../server/api/albums/[albumName].patch'
import albumsGetHandler from '../../server/api/albums/index.get'
import albumsPostHandler from '../../server/api/albums/index.post'
import { attachRequestLogger } from '../../server/middleware/00.request-logger'
import { getAlbums, invalidateAlbumsCache } from '../../server/utils/albums-cache'
import { invalidateFileDatabaseCache } from '../../server/utils/file-database-cache'
import { setMockRuntimeConfig } from '../nuxt-imports-stub'

const HASH_1 = 'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678'
const HASH_2 = '0123456789abcdef0123456789abcdef01234567'
const HASH_DANGLING = 'ffffffffffffffffffffffffffffffffffffffff'

const makeAlbumEvent = (
  path: string,
  options: {
    method?: string
    body?: unknown
    params?: Record<string, string>
  } = {}
): H3Event => {
  const req = new IncomingMessage(new Socket())
  req.url = path
  req.method = options.method || 'GET'
  req.headers.authorization = 'Bearer tok-albums'
  if (options.body !== undefined) {
    const raw = JSON.stringify(options.body)
    req.headers['content-type'] = 'application/json'
    req.headers['content-length'] = String(Buffer.byteLength(raw))
    req.push(raw)
    req.push(null)
  }
  const res = new ServerResponse(req)
  const event = createEvent(req, res)
  if (options.params) {
    event.context.params = options.params
  }
  event.context.auth = { uid: 'u1', email: 'user@example.com', email_verified: true }
  event.context.idToken = 'tok-albums'
  attachRequestLogger(event)
  return event
}

describe('Writable Albums CRUD, Optimistic Concurrency & Rollback Safety', () => {
  const tempDirs: string[] = []
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    invalidateAlbumsCache()
    invalidateFileDatabaseCache()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    invalidateAlbumsCache()
    invalidateFileDatabaseCache()
    for (const dir of tempDirs.splice(0)) {
      rmSync(dir, { recursive: true, force: true })
    }
  })

  const setupTestStorage = (options: { uploadMode?: 'ok' | '412' | '500' } = {}) => {
    const vol = mkdtempSync(resolve(tmpdir(), 'ps-albums-'))
    tempDirs.push(vol)

    setMockRuntimeConfig({
      storage: { dataBucket: 'data-bkt', mediaBucket: 'media-bkt', mountedVolumePath: vol },
      database: {
        jsonFileName: 'photosphere_database_cloud.json',
        labelsJsonFileName: 'photosphere_image_labelling_database_cloud.json',
        captionsJsonFileName: 'photosphere_image_caption_database_cloud.json',
        albumsJsonFileName: 'photosphere_albums.json',
      },
    })

    const mediaDb = {
      [HASH_1]: {
        hash: HASH_1,
        average_hash: null,
        source_bucket_uri: 'gs://media-bkt/1.jpg',
        thumbnail_bucket_uri: 'gs://media-bkt/t1.jpg',
        file_type: 'IMAGE',
        created_at: null,
        created_at_timestamp: 200,
        latitude: null,
        longitude: null,
        geohash: null,
        label_indexes: [],
        caption_index: null,
      },
      [HASH_2]: {
        hash: HASH_2,
        average_hash: null,
        source_bucket_uri: 'gs://media-bkt/2.mp4',
        thumbnail_bucket_uri: 'gs://media-bkt/t2.jpg',
        file_type: 'VIDEO',
        created_at: null,
        created_at_timestamp: 100,
        latitude: null,
        longitude: null,
        geohash: null,
        label_indexes: [],
        caption_index: null,
      },
    }

    let remoteGeneration = 100
    let remoteAlbums = [{ name: 'Milan 2024', hashes: [HASH_1, HASH_DANGLING] }]
    let currentUploadMode = options.uploadMode || 'ok'

    const fetchMock = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const target = String(url)
      if (target.includes('photosphere_database_cloud.json')) {
        return new Response(JSON.stringify(mediaDb), { status: 200 })
      }
      if (target.includes('photosphere_albums.json') && init?.method === 'POST') {
        if (currentUploadMode === '412') {
          return new Response('precondition failed', { status: 412 })
        }
        if (currentUploadMode === '500') {
          return new Response('upstream error', { status: 500 })
        }
        const expectedGen = (init.headers as Record<string, string>)['x-goog-if-generation-match']
        expect(expectedGen).toBe(String(remoteGeneration))
        remoteAlbums = JSON.parse(String(init.body))
        remoteGeneration += 1
        return new Response(JSON.stringify({ generation: String(remoteGeneration) }), {
          status: 200,
          headers: { 'x-goog-generation': String(remoteGeneration) },
        })
      }
      return new Response(JSON.stringify(remoteAlbums), {
        status: 200,
        headers: { 'x-goog-generation': String(remoteGeneration) },
      })
    }) as unknown as typeof fetch

    globalThis.fetch = fetchMock
    return {
      vol,
      setUploadMode: (m: 'ok' | '412' | '500') => {
        currentUploadMode = m
      },
    }
  }

  it('lists paginated albums with filtered cover thumbnails and supports full CRUD lifecycle', async () => {
    const { vol } = setupTestStorage()

    // GET /api/albums filters out HASH_DANGLING from coverThumbnails
    const initialList = await albumsGetHandler(makeAlbumEvent('/api/albums?page=1&limit=20'))
    expect(initialList.totalCount).toBe(1)
    expect(initialList.items[0]).toEqual({
      name: 'Milan 2024',
      totalFiles: 2,
      coverThumbnails: [`/api/media/${HASH_1}?variant=thumbnail`],
    })

    // POST /api/albums creates album & logs album_mutated
    const postEv = makeAlbumEvent('/api/albums', {
      method: 'POST',
      body: { name: 'Rome Trip', hashes: [HASH_2] },
    })
    const postSpy = vi.spyOn(postEv.context.logger!, 'info')
    const created = await albumsPostHandler(postEv)
    expect(created.album).toEqual({
      name: 'Rome Trip',
      totalFiles: 1,
      coverThumbnails: [`/api/media/${HASH_2}?variant=thumbnail`],
    })
    expect(postSpy).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'create', albumName: 'Rome Trip', hashCount: 1 }),
      'album_mutated'
    )

    // GET /api/albums/[albumName]
    const fetched = await albumGetHandler(
      makeAlbumEvent('/api/albums/Rome%20Trip', { params: { albumName: 'Rome%20Trip' } })
    )
    expect(fetched.name).toBe('Rome Trip')

    // PATCH /api/albums/[albumName] renames, adds, and removes hashes
    const patched = await albumPatchHandler(
      makeAlbumEvent('/api/albums/Rome%20Trip', {
        method: 'PATCH',
        params: { albumName: 'Rome%20Trip' },
        body: { newName: 'Italy Roadtrip', addHashes: [HASH_1, HASH_2], removeHashes: [HASH_2] },
      })
    )
    expect(patched.album).toEqual({
      name: 'Italy Roadtrip',
      totalFiles: 1,
      coverThumbnails: [`/api/media/${HASH_1}?variant=thumbnail`],
    })

    // Disk cache reflects persisted albums
    const diskJson = JSON.parse(readFileSync(resolve(vol, 'photosphere_albums.json'), 'utf-8')) as {
      name: string
      hashes: string[]
    }[]
    expect(diskJson.map((a) => a.name)).toEqual(['Milan 2024', 'Italy Roadtrip'])

    // DELETE /api/albums/[albumName]
    const deleted = await albumDeleteHandler(
      makeAlbumEvent('/api/albums/Italy%20Roadtrip', {
        method: 'DELETE',
        params: { albumName: 'Italy%20Roadtrip' },
      })
    )
    expect(deleted).toEqual({ deleted: true, name: 'Italy Roadtrip' })
    expect(
      await getAlbums('tok-albums', { dataBucket: 'data-bkt', mountedVolumePath: vol })
    ).toHaveLength(1)
  })

  it('rejects invalid album names, case-insensitive duplicates, and preserves caches on GCS upload failure', async () => {
    const { vol, setUploadMode } = setupTestStorage()

    // Prime initial cache
    await albumsGetHandler(makeAlbumEvent('/api/albums'))
    const diskBefore = readFileSync(resolve(vol, 'photosphere_albums.json'), 'utf-8')

    // Invalid names -> 400
    await expect(
      albumsPostHandler(makeAlbumEvent('/api/albums', { method: 'POST', body: { name: '   ' } }))
    ).rejects.toMatchObject({ statusCode: 400 })
    await expect(
      albumsPostHandler(
        makeAlbumEvent('/api/albums', { method: 'POST', body: { name: 'Bad/Name' } })
      )
    ).rejects.toMatchObject({ statusCode: 400 })

    // Case-insensitive duplicate -> 409
    await expect(
      albumsPostHandler(
        makeAlbumEvent('/api/albums', { method: 'POST', body: { name: 'milan 2024' } })
      )
    ).rejects.toMatchObject({ statusCode: 409 })

    // 412 Precondition Failed -> 409 Conflict with zero disk or memory mutation
    setUploadMode('412')
    await expect(
      albumsPostHandler(
        makeAlbumEvent('/api/albums', { method: 'POST', body: { name: 'Concurrent Album' } })
      )
    ).rejects.toMatchObject({ statusCode: 409 })
    expect(readFileSync(resolve(vol, 'photosphere_albums.json'), 'utf-8')).toBe(diskBefore)
    expect(
      (await getAlbums('tok-albums', { dataBucket: 'data-bkt', mountedVolumePath: vol })).map(
        (a) => a.name
      )
    ).toEqual(['Milan 2024'])

    // Upstream 500 -> 502 with zero disk or memory mutation
    setUploadMode('500')
    await expect(
      albumPatchHandler(
        makeAlbumEvent('/api/albums/Milan%202024', {
          method: 'PATCH',
          params: { albumName: 'Milan%202024' },
          body: { newName: 'Changed Name' },
        })
      )
    ).rejects.toMatchObject({ statusCode: 502 })
    expect(readFileSync(resolve(vol, 'photosphere_albums.json'), 'utf-8')).toBe(diskBefore)
    expect(
      (await getAlbums('tok-albums', { dataBucket: 'data-bkt', mountedVolumePath: vol })).map(
        (a) => a.name
      )
    ).toEqual(['Milan 2024'])
  })

  it('preserves GCS ifGenerationMatch across warm disk-cache restarts via .meta.json sidecar', async () => {
    const { vol } = setupTestStorage()

    // Prime disk cache and .meta.json sidecar
    await albumsGetHandler(makeAlbumEvent('/api/albums'))
    const metaRaw = JSON.parse(
      readFileSync(resolve(vol, 'photosphere_albums.json.meta.json'), 'utf-8')
    ) as { generation: string }
    expect(metaRaw.generation).toBe('100')

    // Simulate process restart by clearing in-memory cache while preserving disk files
    invalidateAlbumsCache()

    const patched = await albumPatchHandler(
      makeAlbumEvent('/api/albums/Milan%202024', {
        method: 'PATCH',
        params: { albumName: 'Milan%202024' },
        body: { newName: 'Milan Warm Restart' },
      })
    )
    expect(patched.album?.name).toBe('Milan Warm Restart')
    const updatedMeta = JSON.parse(
      readFileSync(resolve(vol, 'photosphere_albums.json.meta.json'), 'utf-8')
    ) as { generation: string }
    expect(updatedMeta.generation).toBe('101')
  })
})

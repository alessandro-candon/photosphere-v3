import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createAlbum,
  deleteAlbum,
  getAlbums,
  invalidateAlbumsCache,
  updateAlbum,
} from '../../server/utils/albums-cache'
import {
  matchesMediaFilters,
  normalizeLanguageCode,
  parsePagination,
} from '../../server/utils/file-filters'
import { toProxyUrl } from '../../server/utils/url'
import type { HydratedMediaItem } from '../../server/types/cache'

describe('Albums CRUD Mutations, Proxy URLs, and Media Filters', () => {
  const tempDirs: string[] = []
  const HASH_A = 'a'.repeat(40)
  const HASH_B = 'b'.repeat(40)

  afterEach(() => {
    invalidateAlbumsCache()
    for (const dir of tempDirs.splice(0)) {
      rmSync(dir, { recursive: true, force: true })
    }
  })

  it('creates, updates, deletes albums in dataBucket and syncs local + in-memory cache', async () => {
    const vol = mkdtempSync(resolve(tmpdir(), 'ps-alb-'))
    tempDirs.push(vol)
    let remoteAlbums = '[]'

    const fetchMock = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      if (init?.method === 'POST') {
        remoteAlbums = String(init.body)
        return new Response(remoteAlbums, { status: 200 })
      }
      return new Response(remoteAlbums, { status: 200 })
    }) as unknown as typeof fetch

    const opts = {
      dataBucket: 'data-std',
      mountedVolumePath: vol,
      fetchImpl: fetchMock,
    }

    const created = await createAlbum('Milan 2025', [HASH_A], 'tok', opts)
    expect(created).toEqual({ name: 'Milan 2025', hashes: [HASH_A] })
    expect(existsSync(resolve(vol, 'photosphere_albums.json'))).toBe(true)
    expect(JSON.parse(readFileSync(resolve(vol, 'photosphere_albums.json'), 'utf-8'))).toHaveLength(
      1
    )

    await expect(createAlbum('milan 2025', [HASH_A], 'tok', opts)).rejects.toMatchObject({
      statusCode: 409,
    })

    const updated = await updateAlbum('Milan 2025', [HASH_A, HASH_B, HASH_A], 'tok', opts)
    expect(updated.hashes).toEqual([HASH_A, HASH_B])
    expect(await getAlbums('tok', opts)).toEqual([{ name: 'Milan 2025', hashes: [HASH_A, HASH_B] }])

    await deleteAlbum('Milan 2025', 'tok', opts)
    expect(await getAlbums('tok', opts)).toEqual([])
    expect(JSON.parse(remoteAlbums)).toEqual([])

    await expect(updateAlbum('Missing', [HASH_A], 'tok', opts)).rejects.toMatchObject({
      statusCode: 404,
    })
    await expect(deleteAlbum('Missing', 'tok', opts)).rejects.toMatchObject({
      statusCode: 404,
    })
    await expect(createAlbum('   ', [HASH_A], 'tok', opts)).rejects.toMatchObject({
      statusCode: 400,
    })
    await expect(createAlbum('BadHash', ['not-a-sha1'], 'tok', opts)).rejects.toMatchObject({
      statusCode: 400,
    })

    invalidateAlbumsCache()
    const vol404 = mkdtempSync(resolve(tmpdir(), 'ps-alb-404-'))
    tempDirs.push(vol404)
    const fetch404 = vi.fn(
      async () => new Response('none', { status: 404 })
    ) as unknown as typeof fetch
    expect(
      await getAlbums('tok', {
        dataBucket: 'data-std',
        mountedVolumePath: vol404,
        fetchImpl: fetch404,
      })
    ).toEqual([])
  })

  it('validates Proxy URLs, traversal segments, language normalization, and media filters', () => {
    expect(toProxyUrl('gs://media-arch/2025/05/photo one.jpg', 'media-arch')).toBe(
      '/api/img/2025/05/photo%20one.jpg'
    )
    expect(toProxyUrl('gs://other-bkt/2025/05/photo.jpg', 'media-arch')).toBeNull()
    expect(toProxyUrl('gs://media-arch/../secret.txt', 'media-arch')).toBeNull()
    expect(toProxyUrl(null, 'media-arch')).toBeNull()

    expect(normalizeLanguageCode('IT')).toBe('it')
    expect(normalizeLanguageCode(123)).toBe('en')
    expect(normalizeLanguageCode('invalid lang!')).toBe('en')
    expect(parsePagination('2', '500')).toEqual({ page: 2, limit: 200 })

    const item: HydratedMediaItem = {
      hash: HASH_A,
      averageHash: 'ffff',
      fileType: 'IMAGE',
      createdAt: '2025-05-01T10:00:00Z',
      createdAtTimestamp: 1746093600,
      latitude: 45.4,
      longitude: 9.1,
      geohash: 'u0nd9',
      labels: ['mountain', 'sunrise'],
      caption: 'Alps sunrise view',
      proxyUrls: { sourceUrl: '/api/img/a.jpg', thumbnailUrl: '/api/img/thumbnails/a.jpg' },
    }

    expect(matchesMediaFilters(item, { q: 'sunrise', fileType: 'IMAGE', hasLocation: true })).toBe(
      true
    )
    expect(matchesMediaFilters(item, { q: 'nonexistent-query' })).toBe(false)
    expect(matchesMediaFilters(item, { dateFrom: 2000000000 })).toBe(false)
    expect(matchesMediaFilters(item, { dateTo: 1000000000 })).toBe(false)
    expect(matchesMediaFilters(item, { fileType: 'VIDEO' })).toBe(false)
    expect(matchesMediaFilters(item, { albumHashes: new Set([HASH_B]) })).toBe(false)
  })
})

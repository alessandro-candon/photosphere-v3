import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  getAlbums,
  invalidateAlbumsCache,
  validateAlbumsPayload,
} from '../../server/utils/albums-cache'
import {
  applyConfigToProcessEnv,
  loadPhotosphereConfig,
  validatePhotosphereConfig,
} from '../../server/utils/photosphere-config'
import {
  getLanguageDictionaries,
  getMediaDatabase,
  invalidateFileDatabaseCache,
  normalizeLanguageCode,
  sortMediaHashesDescending,
  validateMediaDatabasePayload,
} from '../../server/utils/file-database-cache'

const CONTRACTS_FIXTURES_DIR = resolve(__dirname, '../../../contracts/fixtures')

const loadFixture = (name: string): unknown =>
  JSON.parse(readFileSync(resolve(CONTRACTS_FIXTURES_DIR, name), 'utf-8'))

describe('v3 JSON Database Contract Parity', () => {
  const tempDirs: string[] = []

  afterEach(() => {
    invalidateFileDatabaseCache()
    invalidateAlbumsCache()
    for (const dir of tempDirs.splice(0)) {
      rmSync(dir, { recursive: true, force: true })
    }
  })

  it('parses canonical valid_media_db.json fixture and pre-sorts descending by timestamp', () => {
    const validDb = loadFixture('valid_media_db.json')
    const parsed = validateMediaDatabasePayload(validDb)
    expect(Object.keys(parsed)).toHaveLength(2)

    const sorted = sortMediaHashesDescending(parsed)
    const newerHash = '0123456789abcdef0123456789abcdef01234567'
    const olderHash = 'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678'
    expect(sorted).toEqual([newerHash, olderHash])

    expect(normalizeLanguageCode('IT')).toBe('it')
    expect(normalizeLanguageCode(123)).toBe('en')
    expect(normalizeLanguageCode('invalid lang!')).toBe('en')
  })

  it('rejects legacy TinyDB _default wrapper and local_file_path with 500 error', () => {
    const legacy = loadFixture('legacy_v2_tinydb.json')
    expect(() => validateMediaDatabasePayload(legacy)).toThrowError(/TinyDB _default/)

    const valid = loadFixture('valid_media_db.json') as Record<string, Record<string, unknown>>
    const firstKey = Object.keys(valid)[0]!
    valid[firstKey]!.local_file_path = '/Users/me/secret.jpg'
    expect(() => validateMediaDatabasePayload(valid)).toThrowError(/local_file_path/)
  })

  it('loads media DB, language dictionaries with en_ fallback, and albums from dataBucket', async () => {
    const vol = mkdtempSync(resolve(tmpdir(), 'ps-db-'))
    tempDirs.push(vol)

    const validDbRaw = readFileSync(resolve(CONTRACTS_FIXTURES_DIR, 'valid_media_db.json'), 'utf-8')
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

    const fetchMock = vi.fn(async (url: string | URL | Request) => {
      const target = String(url)
      expect(target).toContain('test-data-standard')
      if (target.includes('fr_')) {
        return new Response('not found', { status: 404 })
      }
      if (target.includes('labelling')) {
        return new Response(validLabelsRaw, { status: 200 })
      }
      if (target.includes('caption')) {
        return new Response(validCaptionsRaw, { status: 200 })
      }
      if (target.includes('albums')) {
        return new Response(validAlbumsRaw, { status: 200 })
      }
      return new Response(validDbRaw, { status: 200 })
    }) as unknown as typeof fetch

    const snapshot = await getMediaDatabase('tok-123', {
      dataBucket: 'test-data-standard',
      mountedVolumePath: vol,
      fetchImpl: fetchMock,
    })
    expect(snapshot.sortedHashes).toHaveLength(2)

    const dicts = await getLanguageDictionaries('fr', 'tok-123', {
      dataBucket: 'test-data-standard',
      mountedVolumePath: vol,
      fetchImpl: fetchMock,
    })
    expect(dicts.labels['0']).toBe('dog')
    expect(dicts.captions['0']).toBe('A golden dog running across a sunlit city park.')

    const albums = await getAlbums('tok-123', {
      dataBucket: 'test-data-standard',
      mountedVolumePath: vol,
      fetchImpl: fetchMock,
    })
    expect(albums.length).toBeGreaterThan(0)

    // Remote 404 on dictionaries and albums safely yields empty structures
    invalidateFileDatabaseCache()
    invalidateAlbumsCache()
    const volEmpty = mkdtempSync(resolve(tmpdir(), 'ps-db-empty-'))
    tempDirs.push(volEmpty)
    const fetch404 = vi.fn(
      async () => new Response('missing', { status: 404 })
    ) as unknown as typeof fetch

    const emptyDicts = await getLanguageDictionaries('en', 'tok-123', {
      dataBucket: 'test-data-standard',
      mountedVolumePath: volEmpty,
      fetchImpl: fetch404,
    })
    expect(emptyDicts.labels).toEqual({})
    expect(emptyDicts.captions).toEqual({})

    const emptyAlbums = await getAlbums('tok-123', {
      dataBucket: 'test-data-standard',
      mountedVolumePath: volEmpty,
      fetchImpl: fetch404,
    })
    expect(emptyAlbums).toEqual([])

    expect(() => validateAlbumsPayload('not-an-array')).toThrowError(/expected array/)
    expect(() => validateMediaDatabasePayload(['not-an-object'])).toThrowError(/flat SHA-1/)
    expect(() => validateMediaDatabasePayload({ badkey: {} })).toThrowError(
      /40-char lowercase SHA-1/
    )
    expect(() =>
      validateMediaDatabasePayload({
        ['c'.repeat(40)]: {
          hash: 'd'.repeat(40),
          source_bucket_uri: 'gs://b/a.jpg',
          file_type: 'IMAGE',
          label_indexes: [],
        },
      })
    ).toThrowError(/mismatch/)
  })

  it('validates photosphere.config.json contract, fails fast when missing, and hydrates env', () => {
    const fixture = loadFixture('valid_photosphere_config.json')
    const validated = validatePhotosphereConfig(fixture)
    expect(validated.storage.media_storage_class).toBe('STANDARD')
    expect(validated.auth.allowed_emails).toEqual(['user@example.com'])

    expect(() => loadPhotosphereConfig('/tmp/non-existent-photosphere-config.json')).toThrowError(
      /Missing photosphere\.config\.json/
    )

    const prevMedia = process.env.PHOTOSPHERE_MEDIA_BUCKET
    const prevData = process.env.PHOTOSPHERE_DATA_BUCKET
    try {
      delete process.env.PHOTOSPHERE_MEDIA_BUCKET
      process.env.PHOTOSPHERE_DATA_BUCKET = 'explicit-override-bucket'
      applyConfigToProcessEnv(validated)
      expect(process.env.PHOTOSPHERE_MEDIA_BUCKET).toBe('photosphere-dev-example-media')
      expect(process.env.PHOTOSPHERE_DATA_BUCKET).toBe('explicit-override-bucket')
    } finally {
      if (prevMedia === undefined) {
        delete process.env.PHOTOSPHERE_MEDIA_BUCKET
      } else {
        process.env.PHOTOSPHERE_MEDIA_BUCKET = prevMedia
      }
      if (prevData === undefined) {
        delete process.env.PHOTOSPHERE_DATA_BUCKET
      } else {
        process.env.PHOTOSPHERE_DATA_BUCKET = prevData
      }
    }
  })
})

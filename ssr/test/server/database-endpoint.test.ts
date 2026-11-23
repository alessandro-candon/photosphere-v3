import { IncomingMessage, ServerResponse } from 'node:http'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { Socket } from 'node:net'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { createEvent, type H3Event } from 'h3'
import { afterEach, describe, expect, it, vi } from 'vitest'
import databaseHandler from '../../server/api/database/index.get'
import { invalidateAlbumsCache } from '../../server/utils/albums-cache'
import { invalidateFileDatabaseCache } from '../../server/utils/file-database-cache'
import { setMockRuntimeConfig } from '../nuxt-imports-stub'

const CONTRACTS_FIXTURES_DIR = resolve(__dirname, '../../../contracts/fixtures')

const makeEvent = (path: string, authorization?: string, email?: string): H3Event => {
  const req = new IncomingMessage(new Socket())
  req.url = path
  req.method = 'GET'
  if (authorization) {
    req.headers.authorization = authorization
  }
  const res = new ServerResponse(req)
  const event = createEvent(req, res)
  if (email) {
    event.context.auth = {
      uid: 'uid-1',
      email,
      email_verified: true,
    }
  }
  return event
}

describe('GET /api/database handler (admin-only)', () => {
  const tempDirs: string[] = []
  const originalFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = originalFetch
    invalidateFileDatabaseCache()
    invalidateAlbumsCache()
    for (const dir of tempDirs.splice(0)) {
      rmSync(dir, { recursive: true, force: true })
    }
  })

  it('rejects non-admin users with 403', async () => {
    setMockRuntimeConfig({
      auth: {
        allowedEmails: ['user@example.com', 'admin@example.com'],
        adminEmail: 'admin@example.com',
      },
    })

    await expect(
      databaseHandler(makeEvent('/api/database?lang=en', 'Bearer test-token', 'user@example.com'))
    ).rejects.toMatchObject({ statusCode: 403 })
  })

  it('returns raw JSON payloads and counts for admin users', async () => {
    const vol = mkdtempSync(resolve(tmpdir(), 'ps-db-api-'))
    tempDirs.push(vol)

    setMockRuntimeConfig({
      public: { defaultLang: 'en' },
      storage: {
        dataBucket: 'test-data-bucket',
        mediaBucket: 'test-media-bucket',
        mountedVolumePath: vol,
      },
      auth: {
        allowedEmails: ['user@example.com', 'admin@example.com'],
        adminEmail: 'admin@example.com',
      },
      database: {
        jsonFileName: 'photosphere_database_cloud.json',
        labelsJsonFileName: 'photosphere_image_labelling_database_cloud.json',
        captionsJsonFileName: 'photosphere_image_caption_database_cloud.json',
        albumsJsonFileName: 'photosphere_albums.json',
      },
    })

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

    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const target = String(url)
      if (target.includes('labelling')) return new Response(validLabelsRaw, { status: 200 })
      if (target.includes('caption')) return new Response(validCaptionsRaw, { status: 200 })
      if (target.includes('albums')) return new Response(validAlbumsRaw, { status: 200 })
      return new Response(validDbRaw, { status: 200 })
    }) as unknown as typeof fetch

    const result = await databaseHandler(
      makeEvent('/api/database?lang=en', 'Bearer test-token', 'admin@example.com')
    )

    expect(result.lang).toBe('en')
    expect(result.files.mediaDb.fileName).toBe('photosphere_database_cloud.json')
    expect(result.files.mediaDb.count).toBe(2)
    expect(result.files.labels.fileName).toBe('en_photosphere_image_labelling_database_cloud.json')
    expect(result.files.labels.data['0']).toBe('dog')
    expect(result.files.captions.fileName).toBe('en_photosphere_image_caption_database_cloud.json')
    expect(result.files.captions.data['0']).toContain('golden dog')
    expect(result.files.albums.fileName).toBe('photosphere_albums.json')
    expect(result.files.albums.count).toBeGreaterThan(0)
  })
})

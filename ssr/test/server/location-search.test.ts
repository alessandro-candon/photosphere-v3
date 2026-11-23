import { IncomingMessage, ServerResponse } from 'node:http'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { Socket } from 'node:net'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { createEvent, type H3Event } from 'h3'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import locationSearchHandler from '../../server/api/location/search.get'
import suggestionsHandler from '../../server/api/search/suggestions.get'
import { attachRequestLogger } from '../../server/middleware/00.request-logger'
import {
  resetLocationProxyForTests,
  searchNominatimLocations,
} from '../../server/services/location-proxy.service'
import { invalidateFileDatabaseCache } from '../../server/utils/file-database-cache'
import { setMockRuntimeConfig } from '../nuxt-imports-stub'

const CONTRACTS_FIXTURES_DIR = resolve(__dirname, '../../../contracts/fixtures')

const makeEvent = (path: string): H3Event => {
  const req = new IncomingMessage(new Socket())
  req.url = path
  req.method = 'GET'
  req.headers.authorization = 'Bearer tok-search'
  const res = new ServerResponse(req)
  const event = createEvent(req, res)
  event.context.auth = { uid: 'u1', email: 'user@example.com', email_verified: true }
  event.context.idToken = 'tok-search'
  attachRequestLogger(event)
  return event
}

describe('GET /api/search/suggestions & GET /api/location/search (OSM Proxy)', () => {
  const tempDirs: string[] = []
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    invalidateFileDatabaseCache()
    resetLocationProxyForTests()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    invalidateFileDatabaseCache()
    resetLocationProxyForTests()
    for (const dir of tempDirs.splice(0)) {
      rmSync(dir, { recursive: true, force: true })
    }
  })

  it('returns unified label and caption suggestions with en fallback', async () => {
    const vol = mkdtempSync(resolve(tmpdir(), 'ps-suggest-'))
    tempDirs.push(vol)

    setMockRuntimeConfig({
      storage: { dataBucket: 'data-bkt', mediaBucket: 'media-bkt', mountedVolumePath: vol },
    })

    const labelsRaw = readFileSync(resolve(CONTRACTS_FIXTURES_DIR, 'valid_en_labels.json'), 'utf-8')
    const captionsRaw = readFileSync(
      resolve(CONTRACTS_FIXTURES_DIR, 'valid_en_captions.json'),
      'utf-8'
    )

    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const target = String(url)
      if (target.includes('fr_')) return new Response('not found', { status: 404 })
      if (target.includes('labelling')) return new Response(labelsRaw, { status: 200 })
      if (target.includes('caption')) return new Response(captionsRaw, { status: 200 })
      return new Response('{}', { status: 200 })
    }) as unknown as typeof fetch

    const res = await suggestionsHandler(makeEvent('/api/search/suggestions?q=dog&lang=fr'))
    expect(res.suggestions).toEqual([
      { text: 'dog', kind: 'label', index: 0 },
      { text: 'A golden dog running across a sunlit city park.', kind: 'caption', index: 0 },
    ])

    const labelsOnly = await suggestionsHandler(
      makeEvent('/api/search/suggestions?q=dog&field=labels&lang=fr')
    )
    expect(labelsOnly.suggestions).toEqual([{ text: 'dog', kind: 'label', index: 0 }])

    const captionsOnly = await suggestionsHandler(
      makeEvent('/api/search/suggestions?q=dog&field=captions&lang=fr')
    )
    expect(captionsOnly.suggestions).toEqual([
      { text: 'A golden dog running across a sunlit city park.', kind: 'caption', index: 0 },
    ])

    await expect(
      suggestionsHandler(makeEvent('/api/search/suggestions?q=dog&field=invalid'))
    ).rejects.toMatchObject({ statusCode: 400 })

    const emptyRes = await suggestionsHandler(makeEvent('/api/search/suggestions?q='))
    expect(emptyRes.suggestions).toEqual([])
  })

  it('caches Nominatim results, throttles concurrent requests, and surfaces upstream errors instead of silent []', async () => {
    setMockRuntimeConfig({
      location: {
        nominatimBaseUrl: 'https://nominatim.test',
        minIntervalMs: 0,
        timeoutMs: 2000,
        userAgent: 'Photosphere-Test/1.0',
      },
    })

    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify([
            {
              place_id: 123,
              display_name: 'Milan, Lombardy, Italy',
              lat: '45.4642',
              lon: '9.1900',
            },
          ]),
          { status: 200 }
        )
    ) as unknown as typeof fetch
    globalThis.fetch = fetchMock

    // Too short query returns empty without hitting fetch
    const shortRes = await locationSearchHandler(makeEvent('/api/location/search?q=a'))
    expect(shortRes.results).toEqual([])
    expect(fetchMock).not.toHaveBeenCalled()

    // First lookup calls upstream
    const first = await locationSearchHandler(makeEvent('/api/location/search?q=Milan'))
    expect(first.results).toEqual([
      { placeId: '123', displayName: 'Milan, Lombardy, Italy', lat: 45.4642, lng: 9.19 },
    ])
    expect(fetchMock).toHaveBeenCalledTimes(1)

    // Repeat lookup (different case) hits LRU cache
    const second = await locationSearchHandler(makeEvent('/api/location/search?q=milan'))
    expect(second.results).toEqual(first.results)
    expect(fetchMock).toHaveBeenCalledTimes(1)

    // Rate limiter sleeps when elapsed < minIntervalMs
    const sleepSpy = vi.fn(async () => {})
    let fakeNow = 10_000
    await searchNominatimLocations(makeEvent('/api/location/search?q=Rome'), 'Rome', {
      baseUrl: 'https://nominatim.test',
      minIntervalMs: 1000,
      timeoutMs: 2000,
      userAgent: 'Test',
      fetchImpl: fetchMock,
      nowFn: () => fakeNow,
      sleepFn: sleepSpy,
    })
    fakeNow += 200 // only 200ms elapsed
    await searchNominatimLocations(makeEvent('/api/location/search?q=Turin'), 'Turin', {
      baseUrl: 'https://nominatim.test',
      minIntervalMs: 1000,
      timeoutMs: 2000,
      userAgent: 'Test',
      fetchImpl: fetchMock,
      nowFn: () => fakeNow,
      sleepFn: sleepSpy,
    })
    expect(sleepSpy).toHaveBeenCalledWith(800)

    // Upstream 500 -> throws 502 and logs location_proxy_failed
    const errEvent = makeEvent('/api/location/search?q=Berlin')
    const warnSpy = vi.spyOn(errEvent.context.logger!, 'warn')
    globalThis.fetch = vi.fn(
      async () => new Response('rate limited', { status: 429 })
    ) as unknown as typeof fetch
    await expect(locationSearchHandler(errEvent)).rejects.toMatchObject({ statusCode: 502 })
    expect(warnSpy).toHaveBeenCalledWith(
      expect.objectContaining({ query: 'Berlin', statusCode: 429 }),
      'location_proxy_failed'
    )

    // Timeout -> throws 504
    const timeoutErr = new Error('The operation timed out')
    timeoutErr.name = 'TimeoutError'
    globalThis.fetch = vi.fn(async () => {
      throw timeoutErr
    }) as unknown as typeof fetch
    await expect(
      locationSearchHandler(makeEvent('/api/location/search?q=Paris'))
    ).rejects.toMatchObject({ statusCode: 504 })
  })
})

import { createError, type H3Event } from 'h3'
import { getEventLogger } from './logger.service'

export interface LocationSearchResultDto {
  placeId: string
  displayName: string
  lat: number
  lng: number
}

interface CacheRecord {
  results: LocationSearchResultDto[]
  expiresAt: number
}

export interface LocationSearchOptions {
  baseUrl: string
  minIntervalMs: number
  timeoutMs: number
  userAgent: string
  fetchImpl?: typeof fetch
  nowFn?: () => number
  sleepFn?: (ms: number) => Promise<void>
}

const MAX_CACHE_ENTRIES = 200
const CACHE_TTL_MS = 60 * 60 * 1000

const locationCache = new Map<string, CacheRecord>()
let rateLimitQueue: Promise<void> = Promise.resolve()
let lastUpstreamCallAt = 0

export const resetLocationProxyForTests = (): void => {
  locationCache.clear()
  rateLimitQueue = Promise.resolve()
  lastUpstreamCallAt = 0
}

const defaultSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

const runWithRateLimit = async <T>(
  minIntervalMs: number,
  nowFn: () => number,
  sleepFn: (ms: number) => Promise<void>,
  fn: () => Promise<T>
): Promise<T> => {
  const prev = rateLimitQueue
  let release!: () => void
  rateLimitQueue = new Promise<void>((resolve) => {
    release = resolve
  })

  await prev
  try {
    if (minIntervalMs > 0 && lastUpstreamCallAt > 0) {
      const elapsed = nowFn() - lastUpstreamCallAt
      if (elapsed < minIntervalMs) {
        await sleepFn(minIntervalMs - elapsed)
      }
    }
    lastUpstreamCallAt = nowFn()
    return await fn()
  } finally {
    release()
  }
}

export const searchNominatimLocations = async (
  event: H3Event,
  rawQuery: string,
  options: LocationSearchOptions
): Promise<LocationSearchResultDto[]> => {
  const cleanQuery = rawQuery.trim()
  if (cleanQuery.length < 2) {
    return []
  }

  const nowFn = options.nowFn || Date.now
  const sleepFn = options.sleepFn || defaultSleep
  const fetchImpl = options.fetchImpl || globalThis.fetch
  const baseUrl = options.baseUrl.replace(/\/+$/, '')
  const cacheKey = `${baseUrl}|${cleanQuery.toLowerCase()}`

  const cached = locationCache.get(cacheKey)
  if (cached && cached.expiresAt > nowFn()) {
    // Touch LRU entry
    locationCache.delete(cacheKey)
    locationCache.set(cacheKey, cached)
    return cached.results
  }
  if (cached) {
    locationCache.delete(cacheKey)
  }

  return await runWithRateLimit(options.minIntervalMs, nowFn, sleepFn, async () => {
    // Double check cache in case another queued request populated it
    const rechecked = locationCache.get(cacheKey)
    if (rechecked && rechecked.expiresAt > nowFn()) {
      return rechecked.results
    }

    const url = `${baseUrl}/search?format=json&q=${encodeURIComponent(cleanQuery)}&limit=5`
    let response: Response
    const startedAt = nowFn()
    try {
      response = await fetchImpl(url, {
        method: 'GET',
        headers: {
          'User-Agent': options.userAgent,
          Accept: 'application/json',
        },
        signal: AbortSignal.timeout(options.timeoutMs),
      })
    } catch (error) {
      const isTimeout =
        error instanceof Error && (error.name === 'TimeoutError' || error.name === 'AbortError')
      getEventLogger(event).warn(
        {
          query: cleanQuery,
          durationMs: nowFn() - startedAt,
          isTimeout,
          err: error instanceof Error ? error.message : String(error),
        },
        'location_proxy_failed'
      )
      throw createError({
        statusCode: isTimeout ? 504 : 502,
        statusMessage: isTimeout
          ? 'Location search request timed out'
          : 'Failed to reach location search service',
      })
    }

    if (!response.ok) {
      getEventLogger(event).warn(
        {
          query: cleanQuery,
          statusCode: response.status,
          durationMs: nowFn() - startedAt,
        },
        'location_proxy_failed'
      )
      throw createError({
        statusCode: 502,
        statusMessage: `Location search upstream returned ${response.status}`,
      })
    }

    let rawJson: unknown
    try {
      rawJson = await response.json()
    } catch {
      getEventLogger(event).warn(
        {
          query: cleanQuery,
          durationMs: nowFn() - startedAt,
        },
        'location_proxy_failed'
      )
      throw createError({
        statusCode: 502,
        statusMessage: 'Invalid response from location search service',
      })
    }

    if (!Array.isArray(rawJson)) {
      return []
    }

    const results: LocationSearchResultDto[] = rawJson
      .map((item) => {
        const obj = item as Record<string, unknown>
        const lat = Number(obj.lat)
        const lng = Number(obj.lon)
        if (
          typeof obj.display_name !== 'string' ||
          !Number.isFinite(lat) ||
          !Number.isFinite(lng)
        ) {
          return null
        }
        return {
          placeId: String(obj.place_id ?? `${lat},${lng}`),
          displayName: obj.display_name,
          lat,
          lng,
        }
      })
      .filter((entry): entry is LocationSearchResultDto => entry !== null)

    if (locationCache.size >= MAX_CACHE_ENTRIES) {
      const oldestKey = locationCache.keys().next().value
      if (oldestKey) {
        locationCache.delete(oldestKey)
      }
    }
    locationCache.set(cacheKey, {
      results,
      expiresAt: nowFn() + CACHE_TTL_MS,
    })

    return results
  })
}

import { createError, defineEventHandler, getQuery } from 'h3'
import { getEventLogger } from '../../services/logger.service'

export interface LocationSearchResult {
  displayName: string
  lat: number
  lon: number
  boundingBox: [string, string, string, string] | null
}

interface NominatimItem {
  display_name?: string
  lat?: string
  lon?: string
  boundingbox?: [string, string, string, string]
}

export default defineEventHandler(async (event) => {
  const query = getQuery(event)
  const q = typeof query.q === 'string' ? query.q.trim() : ''
  if (!q) {
    throw createError({ statusCode: 400, statusMessage: 'Query parameter q is required' })
  }

  const limitRaw = Number.parseInt(String(query.limit ?? '8'), 10)
  const limit = Number.isFinite(limitRaw) && limitRaw > 0 ? Math.min(limitRaw, 20) : 8

  const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(q)}&limit=${limit}`
  let response: Response
  try {
    response = await fetch(url, {
      headers: {
        'User-Agent': 'photosphere-ssr/3.0',
        Accept: 'application/json',
      },
      signal: AbortSignal.timeout(5000),
    })
  } catch (error) {
    getEventLogger(event).warn({ err: String(error), q }, 'location_upstream_request_failed')
    throw createError({
      statusCode: 502,
      statusMessage: 'Upstream location geocoding service request failed',
    })
  }

  if (!response.ok) {
    getEventLogger(event).warn({ status: response.status, q }, 'location_upstream_bad_status')
    throw createError({
      statusCode: 502,
      statusMessage: `Upstream location service returned HTTP ${response.status}`,
    })
  }

  const data = (await response.json()) as NominatimItem[]
  const results: LocationSearchResult[] = data
    .map((item) => ({
      displayName: item.display_name || '',
      lat: Number.parseFloat(item.lat || ''),
      lon: Number.parseFloat(item.lon || ''),
      boundingBox: Array.isArray(item.boundingbox) ? item.boundingbox : null,
    }))
    .filter(
      (item) => Boolean(item.displayName) && Number.isFinite(item.lat) && Number.isFinite(item.lon)
    )

  return { results }
})

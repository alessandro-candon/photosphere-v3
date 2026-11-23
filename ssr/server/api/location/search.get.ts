import { defineEventHandler, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import { searchNominatimLocations } from '../../services/location-proxy.service'

export default defineEventHandler(async (event) => {
  const query = getQuery(event)
  const rawQ = typeof query.q === 'string' ? query.q : ''
  const cfg = useRuntimeConfig(event)

  const results = await searchNominatimLocations(event, rawQ, {
    baseUrl: cfg.location?.nominatimBaseUrl || 'https://nominatim.openstreetmap.org',
    minIntervalMs: cfg.location?.minIntervalMs ?? 1000,
    timeoutMs: cfg.location?.timeoutMs ?? 5000,
    userAgent: cfg.location?.userAgent || 'Photosphere-v3/1.0',
  })

  return { results }
})

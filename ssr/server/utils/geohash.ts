import type { GeohashPrecision } from '../types/cache'

const BASE32_ALPHABET = '0123456789bcdefghjkmnpqrstuvwxyz'

export const GEOHASH_PRECISIONS: readonly GeohashPrecision[] = [2, 3, 4, 5, 6] as const

export const isValidCoordinatePair = (lat: unknown, lng: unknown): lat is number =>
  typeof lat === 'number' &&
  Number.isFinite(lat) &&
  lat >= -90 &&
  lat <= 90 &&
  typeof lng === 'number' &&
  Number.isFinite(lng) &&
  lng >= -180 &&
  lng <= 180

export const encodeGeohash = (lat: number, lng: number, precision = 6): string => {
  const safePrecision = Math.max(1, Math.min(12, Math.floor(precision)))
  let minLat = -90
  let maxLat = 90
  let minLng = -180
  let maxLng = 180

  let isEven = true
  let bit = 0
  let ch = 0
  let hash = ''

  while (hash.length < safePrecision) {
    if (isEven) {
      const mid = (minLng + maxLng) / 2
      if (lng >= mid) {
        ch = (ch << 1) | 1
        minLng = mid
      } else {
        ch = ch << 1
        maxLng = mid
      }
    } else {
      const mid = (minLat + maxLat) / 2
      if (lat >= mid) {
        ch = (ch << 1) | 1
        minLat = mid
      } else {
        ch = ch << 1
        maxLat = mid
      }
    }

    isEven = !isEven
    bit += 1

    if (bit === 5) {
      hash += BASE32_ALPHABET[ch]
      bit = 0
      ch = 0
    }
  }

  return hash
}

export const resolveGeohashPrecision = (zoom: number): GeohashPrecision => {
  if (!Number.isFinite(zoom) || zoom <= 3) return 2
  if (zoom <= 5) return 3
  if (zoom <= 8) return 4
  if (zoom <= 11) return 5
  return 6
}

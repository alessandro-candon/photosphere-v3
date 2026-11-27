export const toEpochMilliseconds = (timestamp: number): number =>
  Math.abs(timestamp) < 1e11 ? timestamp * 1000 : timestamp

const toValidDate = (timestamp: number | null | undefined): Date | null => {
  if (timestamp === null || timestamp === undefined || !Number.isFinite(timestamp)) {
    return null
  }
  const date = new Date(toEpochMilliseconds(timestamp))
  return Number.isNaN(date.getTime()) ? null : date
}

export const formatUtcMonthDay = (timestamp: number): string | null => {
  const date = toValidDate(timestamp)
  if (!date) {
    return null
  }
  const month = String(date.getUTCMonth() + 1).padStart(2, '0')
  const day = String(date.getUTCDate()).padStart(2, '0')
  return `${month}-${day}`
}

/**
 * Day-section grouping key for MediaTimelineGrid (date-only + 'Undated' fallback).
 */
export const formatTimelineDateGroup = (timestamp: number | null | undefined): string => {
  const date = toValidDate(timestamp)
  if (!date) {
    return 'Undated'
  }
  return date.toLocaleDateString(undefined, {
    weekday: 'short',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/**
 * Full date+time string for MediaLightbox (returns '' when timestamp and fallback are missing).
 */
export const formatMediaDateTime = (
  timestamp: number | null | undefined,
  fallbackIso?: string | null
): string => {
  const date = toValidDate(timestamp)
  if (!date) {
    return fallbackIso || ''
  }
  return date.toLocaleString()
}

/**
 * Compact date string for MapInspectDrawer cards (returns 'Unknown date' when missing).
 */
export const formatCompactDate = (iso: string | null | undefined): string => {
  if (!iso) return 'Unknown date'
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return iso
  return parsed.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

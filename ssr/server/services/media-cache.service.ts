import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync } from 'node:fs'
import { resolve } from 'node:path'
import { createError, getHeader, setHeader, setResponseStatus, type H3Event } from 'h3'
import { getEventLogger } from './logger.service'
import type { MediaFileType } from '../types/cache'
import {
  downloadMediaObject,
  writeFileAtomic,
  type StorageOptions,
} from '../utils/storage-download'

export type MediaVariant = 'thumbnail' | 'source'

interface LruEntry {
  key: string
  dataPath: string
  metaPath: string
  sizeBytes: number
  contentType: string
}

interface CacheDirState {
  hydrated: boolean
  totalBytes: number
  entries: Map<string, LruEntry>
}

export interface ServeMediaInput {
  hash: string
  variant: MediaVariant
  gsUri: string
  fileType: MediaFileType
  idToken: string
  mediaCacheDir: string
  maxCacheBytes: number
  maxCacheableVideoBytes: number
  storageOptions?: StorageOptions
}

const cacheStateByDir = new Map<string, CacheDirState>()

export const resetMediaLruCacheForTests = (): void => {
  cacheStateByDir.clear()
}

const EXTENSION_MIME_MAP: Record<string, string> = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
  gif: 'image/gif',
  heic: 'image/heic',
  mp4: 'video/mp4',
  mov: 'video/quicktime',
  webm: 'video/webm',
  mkv: 'video/x-matroska',
}

export const inferMediaContentType = (gsUri: string, upstreamType?: string | null): string => {
  const cleanUpstream = (upstreamType || '').split(';')[0]?.trim().toLowerCase()
  if (cleanUpstream && cleanUpstream !== 'application/octet-stream') {
    return cleanUpstream
  }
  const cleanUri = gsUri.split('?')[0] || ''
  const dotIdx = cleanUri.lastIndexOf('.')
  if (dotIdx !== -1) {
    const ext = cleanUri.slice(dotIdx + 1).toLowerCase()
    if (EXTENSION_MIME_MAP[ext]) {
      return EXTENSION_MIME_MAP[ext]
    }
  }
  return cleanUpstream || 'application/octet-stream'
}

const getCacheState = (cacheDir: string): CacheDirState => {
  let state = cacheStateByDir.get(cacheDir)
  if (state?.hydrated) {
    return state
  }

  mkdirSync(cacheDir, { recursive: true })
  const entries = new Map<string, LruEntry>()
  let totalBytes = 0

  const dirFiles = readdirSync(cacheDir)
  const diskItems: { entry: LruEntry; mtimeMs: number }[] = []

  for (const name of dirFiles) {
    if (!name.endsWith('.bin')) continue
    const base = name.slice(0, -4)
    const dotIdx = base.indexOf('.')
    if (dotIdx <= 0) continue
    const hash = base.slice(0, dotIdx)
    const variant = base.slice(dotIdx + 1)
    const key = `${hash}:${variant}`
    const dataPath = resolve(cacheDir, name)
    const metaPath = resolve(cacheDir, `${base}.json`)

    try {
      const stats = statSync(dataPath)
      let contentType = 'application/octet-stream'
      if (existsSync(metaPath)) {
        const parsedMeta = JSON.parse(readFileSync(metaPath, 'utf-8')) as {
          contentType?: string
        }
        if (parsedMeta.contentType) {
          contentType = parsedMeta.contentType
        }
      }
      diskItems.push({
        entry: {
          key,
          dataPath,
          metaPath,
          sizeBytes: stats.size,
          contentType,
        },
        mtimeMs: stats.mtimeMs,
      })
    } catch {
      // Ignore unreadable partial cache entry
    }
  }

  // Sort oldest -> newest so Map insertion order matches LRU eviction order
  diskItems.sort((a, b) => a.mtimeMs - b.mtimeMs)
  for (const item of diskItems) {
    entries.set(item.entry.key, item.entry)
    totalBytes += item.entry.sizeBytes
  }

  state = { hydrated: true, totalBytes, entries }
  cacheStateByDir.set(cacheDir, state)
  return state
}

const touchEntry = (state: CacheDirState, entry: LruEntry): void => {
  state.entries.delete(entry.key)
  state.entries.set(entry.key, entry)
}

const evictIfNeeded = (
  state: CacheDirState,
  maxCacheBytes: number,
  protectedKey: string,
  event: H3Event
): void => {
  if (state.totalBytes <= maxCacheBytes) {
    return
  }

  let evictedCount = 0
  let reclaimedBytes = 0

  for (const [key, entry] of state.entries) {
    if (state.totalBytes <= maxCacheBytes) {
      break
    }
    if (key === protectedKey) {
      continue
    }
    state.entries.delete(key)
    state.totalBytes = Math.max(0, state.totalBytes - entry.sizeBytes)
    reclaimedBytes += entry.sizeBytes
    evictedCount += 1
    rmSync(entry.dataPath, { force: true })
    rmSync(entry.metaPath, { force: true })
  }

  if (evictedCount > 0) {
    getEventLogger(event).info(
      {
        evictedCount,
        reclaimedBytes,
        totalCacheBytes: state.totalBytes,
      },
      'media_cache_eviction'
    )
  }
}

export const parseByteRange = (
  rangeHeader: string,
  totalSize: number
): { start: number; end: number } | null => {
  const match = /^bytes=(\d*)-(\d*)$/i.exec(rangeHeader.trim())
  if (!match) return null

  const [, rawStart, rawEnd] = match
  if (!rawStart && !rawEnd) return null

  if (!rawStart && rawEnd) {
    const suffixLength = parseInt(rawEnd, 10)
    if (!Number.isFinite(suffixLength) || suffixLength <= 0) return null
    const start = Math.max(0, totalSize - suffixLength)
    return { start, end: totalSize - 1 }
  }

  const start = parseInt(rawStart!, 10)
  const end = rawEnd ? parseInt(rawEnd, 10) : totalSize - 1

  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || start >= totalSize) {
    return null
  }
  const clampedEnd = Math.min(end, totalSize - 1)
  if (clampedEnd < start) return null
  return { start, end: clampedEnd }
}

const storeInDiskCache = (
  event: H3Event,
  state: CacheDirState,
  cacheDir: string,
  hash: string,
  variant: MediaVariant,
  data: Uint8Array,
  contentType: string,
  maxCacheBytes: number
): boolean => {
  if (data.byteLength > maxCacheBytes) {
    return false
  }
  const key = `${hash}:${variant}`
  const baseName = `${hash}.${variant}`
  const dataPath = resolve(cacheDir, `${baseName}.bin`)
  const metaPath = resolve(cacheDir, `${baseName}.json`)

  const existing = state.entries.get(key)
  if (existing) {
    state.totalBytes = Math.max(0, state.totalBytes - existing.sizeBytes)
    state.entries.delete(key)
  }

  writeFileAtomic(dataPath, data)
  writeFileAtomic(metaPath, JSON.stringify({ contentType }))

  const entry: LruEntry = {
    key,
    dataPath,
    metaPath,
    sizeBytes: data.byteLength,
    contentType,
  }
  state.entries.set(key, entry)
  state.totalBytes += entry.sizeBytes

  evictIfNeeded(state, maxCacheBytes, key, event)
  return true
}

const sendMediaResponse = (
  event: H3Event,
  bytes: Uint8Array,
  contentType: string,
  etag: string,
  rangeHeader?: string
): { statusCode: number; byteLength: number } => {
  setHeader(event, 'Cache-Control', 'private, max-age=31536000, immutable')
  setHeader(event, 'ETag', etag)
  setHeader(event, 'Accept-Ranges', 'bytes')
  setHeader(event, 'Content-Type', contentType)

  if (rangeHeader) {
    const parsed = parseByteRange(rangeHeader, bytes.byteLength)
    if (!parsed) {
      setHeader(event, 'Content-Range', `bytes */${bytes.byteLength}`)
      throw createError({
        statusCode: 416,
        statusMessage: 'Range Not Satisfiable',
      })
    }
    const slice = bytes.subarray(parsed.start, parsed.end + 1)
    setResponseStatus(event, 206)
    setHeader(event, 'Content-Range', `bytes ${parsed.start}-${parsed.end}/${bytes.byteLength}`)
    setHeader(event, 'Content-Length', slice.byteLength)
    return { statusCode: 206, byteLength: slice.byteLength }
  }

  setResponseStatus(event, 200)
  setHeader(event, 'Content-Length', bytes.byteLength)
  return { statusCode: 200, byteLength: bytes.byteLength }
}

export const serveMediaFromCache = async (
  event: H3Event,
  input: ServeMediaInput
): Promise<Uint8Array | null> => {
  const {
    hash,
    variant,
    gsUri,
    fileType,
    idToken,
    mediaCacheDir,
    maxCacheBytes,
    maxCacheableVideoBytes,
    storageOptions,
  } = input

  const etag = `"${hash}-${variant}"`
  const ifNoneMatch = getHeader(event, 'if-none-match')
  if (ifNoneMatch && ifNoneMatch.split(',').some((tag) => tag.trim() === etag)) {
    setHeader(event, 'Cache-Control', 'private, max-age=31536000, immutable')
    setHeader(event, 'ETag', etag)
    setResponseStatus(event, 304)
    return null
  }

  const rangeHeader = getHeader(event, 'range')
  const isRangeRequest = Boolean(rangeHeader)
  const state = getCacheState(mediaCacheDir)
  const key = `${hash}:${variant}`
  const cachedEntry = state.entries.get(key)

  if (cachedEntry && existsSync(cachedEntry.dataPath)) {
    const fullBytes = new Uint8Array(readFileSync(cachedEntry.dataPath))
    touchEntry(state, cachedEntry)
    const sent = sendMediaResponse(event, fullBytes, cachedEntry.contentType, etag, rangeHeader)
    getEventLogger(event).debug(
      {
        hash,
        variant,
        bytes: sent.byteLength,
        isRangeRequest,
        statusCode: sent.statusCode,
      },
      'media_cache_hit'
    )
    if (sent.statusCode === 206 && rangeHeader) {
      const parsed = parseByteRange(rangeHeader, fullBytes.byteLength)!
      return fullBytes.subarray(parsed.start, parsed.end + 1)
    }
    return fullBytes
  }

  const startMs = Date.now()
  try {
    const upstream = await downloadMediaObject(gsUri, idToken, {
      ...storageOptions,
      rangeHeader: variant === 'source' && fileType === 'VIDEO' ? rangeHeader : undefined,
    })

    const contentType = inferMediaContentType(gsUri, upstream.contentType)
    const gcsDurationMs = Date.now() - startMs

    // Check if an upstream 206 actually delivered the full object within video cache budget
    let fullObjectDelivered = upstream.status === 200
    if (upstream.status === 206 && upstream.contentRange) {
      const rangeMatch = /^bytes\s+(\d+)-(\d+)\/(\d+|\*)$/i.exec(upstream.contentRange.trim())
      if (rangeMatch && rangeMatch[3] !== '*') {
        const uStart = Number(rangeMatch[1])
        const uEnd = Number(rangeMatch[2])
        const uTotal = Number(rangeMatch[3])
        if (
          uStart === 0 &&
          uEnd + 1 === uTotal &&
          uTotal === upstream.body.byteLength &&
          uTotal <= maxCacheableVideoBytes
        ) {
          fullObjectDelivered = true
        }
      }
    }

    // Range pass-through when upstream returned a partial chunk of a larger/un-cached object
    if (!fullObjectDelivered && upstream.status === 206 && upstream.contentRange) {
      setResponseStatus(event, 206)
      setHeader(event, 'Cache-Control', 'private, max-age=31536000, immutable')
      setHeader(event, 'ETag', etag)
      setHeader(event, 'Accept-Ranges', 'bytes')
      setHeader(event, 'Content-Type', contentType)
      setHeader(event, 'Content-Range', upstream.contentRange)
      setHeader(event, 'Content-Length', upstream.body.byteLength)

      getEventLogger(event).info(
        {
          hash,
          variant,
          bytes: upstream.body.byteLength,
          gcsDurationMs,
          isRangeRequest: true,
          statusCode: 206,
          cached: false,
        },
        'media_cache_miss'
      )
      return upstream.body
    }

    const withinVideoBudget =
      fileType !== 'VIDEO' || upstream.body.byteLength <= maxCacheableVideoBytes
    const cached = withinVideoBudget
      ? storeInDiskCache(
          event,
          state,
          mediaCacheDir,
          hash,
          variant,
          upstream.body,
          contentType,
          maxCacheBytes
        )
      : false

    const sent = sendMediaResponse(event, upstream.body, contentType, etag, rangeHeader)
    getEventLogger(event).info(
      {
        hash,
        variant,
        bytes: sent.byteLength,
        gcsDurationMs,
        isRangeRequest,
        statusCode: sent.statusCode,
        cached,
      },
      'media_cache_miss'
    )

    if (sent.statusCode === 206 && rangeHeader) {
      const parsed = parseByteRange(rangeHeader, upstream.body.byteLength)!
      return upstream.body.subarray(parsed.start, parsed.end + 1)
    }
    return upstream.body
  } catch (error) {
    getEventLogger(event).warn(
      {
        hash,
        variant,
        err: error instanceof Error ? error.message : String(error),
      },
      'media_proxy_error'
    )
    throw error
  }
}

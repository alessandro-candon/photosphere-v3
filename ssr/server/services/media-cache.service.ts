import { createHash } from 'node:crypto'
import {
  createReadStream,
  existsSync,
  readdirSync,
  readFileSync,
  statSync,
  unlinkSync,
} from 'node:fs'
import { join, resolve } from 'node:path'
import { Readable } from 'node:stream'
import { createError } from 'h3'
import type { BucketTier, CacheTierConfig } from '../types/cache'
import { logger } from '../services/logger.service'
import {
  ensureMountedVolumeDir,
  fetchMediaObject,
  writeFileAtomic,
  type StorageOptions,
} from '../utils/storage-download'

export interface CacheMeta {
  contentType: string
  size: number
  objectPath: string
}

export interface MediaServeResult {
  statusCode: 200 | 206
  contentType: string
  contentLength: number | null
  contentRange?: string
  acceptRanges: 'bytes'
  stream: ReadableStream<Uint8Array> | Readable
  bucketTier: BucketTier
  cacheStatus: 'hit' | 'miss' | 'bypass'
}

export interface MediaCacheConfigs {
  mediaBucket: string
  mountedVolumePath: string
  thumbnailCache: CacheTierConfig
  mediaCache: CacheTierConfig
}

export const resolveBucketTier = (objectPath: string): BucketTier => {
  const normalized = objectPath.replace(/^\/+/, '')
  return normalized.startsWith('thumbnails/') ? 'thumbnail' : 'media'
}

const getCacheKey = (bucket: string, objectPath: string): string =>
  createHash('sha256').update(`${bucket}/${objectPath}`).digest('hex')

const readValidCacheMeta = (
  metaPath: string,
  dataPath: string,
  ttlMs: number
): CacheMeta | null => {
  if (!existsSync(metaPath) || !existsSync(dataPath)) {
    return null
  }
  try {
    const stat = statSync(dataPath)
    if (Date.now() - stat.mtimeMs > ttlMs) {
      return null
    }
    const rawMeta = JSON.parse(readFileSync(metaPath, 'utf-8')) as Partial<CacheMeta>
    if (typeof rawMeta.contentType === 'string' && typeof rawMeta.size === 'number') {
      return {
        contentType: rawMeta.contentType,
        size: stat.size,
        objectPath: rawMeta.objectPath || '',
      }
    }
  } catch {
    return null
  }
  return null
}

export const evictTierCacheIfNeeded = (tierDir: string, maxCacheBytes: number): void => {
  if (!existsSync(tierDir)) {
    return
  }
  const files = readdirSync(tierDir)
    .filter((name) => !name.endsWith('.meta.json') && !name.endsWith('.tmp'))
    .map((name) => {
      const fullPath = join(tierDir, name)
      const stat = statSync(fullPath)
      return { name, fullPath, size: stat.size, mtimeMs: stat.mtimeMs }
    })

  let totalBytes = files.reduce((acc, file) => acc + file.size, 0)
  if (totalBytes <= maxCacheBytes) {
    return
  }

  files.sort((a, b) => a.mtimeMs - b.mtimeMs)
  for (const file of files) {
    if (totalBytes <= maxCacheBytes) {
      break
    }
    try {
      unlinkSync(file.fullPath)
      const metaPath = `${file.fullPath}.meta.json`
      if (existsSync(metaPath)) {
        unlinkSync(metaPath)
      }
      totalBytes -= file.size
    } catch {
      // ignore concurrent unlink
    }
  }
}

export const parseByteRange = (
  rangeHeader: string | undefined,
  totalSize: number
): { start: number; end: number } | null => {
  if (!rangeHeader || !rangeHeader.startsWith('bytes=')) {
    return null
  }
  const spec = rangeHeader.slice('bytes='.length).split(',')[0]?.trim() || ''
  const [rawStart, rawEnd] = spec.split('-')
  if (rawStart === undefined || rawEnd === undefined) {
    return null
  }

  let start: number
  let end: number
  if (rawStart === '' && rawEnd !== '') {
    const suffix = Number.parseInt(rawEnd, 10)
    if (!Number.isFinite(suffix) || suffix <= 0) {
      return null
    }
    start = Math.max(0, totalSize - suffix)
    end = totalSize - 1
  } else {
    start = Number.parseInt(rawStart, 10)
    end = rawEnd === '' ? totalSize - 1 : Number.parseInt(rawEnd, 10)
  }

  if (
    !Number.isFinite(start) ||
    !Number.isFinite(end) ||
    start < 0 ||
    start >= totalSize ||
    start > end
  ) {
    return null
  }
  return { start, end: Math.min(end, totalSize - 1) }
}

export const serveCachedMediaObject = async (
  objectPath: string,
  idToken: string,
  configs: MediaCacheConfigs,
  options?: StorageOptions & { rangeHeader?: string }
): Promise<MediaServeResult> => {
  const cleanObjectPath = objectPath.replace(/^\/+/, '')
  const segments = cleanObjectPath.split('/')
  if (!cleanObjectPath || segments.some((seg) => !seg || seg === '.' || seg === '..')) {
    throw createError({ statusCode: 400, statusMessage: 'Invalid media object path' })
  }

  const bucketTier = resolveBucketTier(cleanObjectPath)
  const tierConfig = bucketTier === 'thumbnail' ? configs.thumbnailCache : configs.mediaCache
  const tierDir = ensureMountedVolumeDir(tierConfig.directoryName, configs.mountedVolumePath)
  const key = getCacheKey(configs.mediaBucket, cleanObjectPath)
  const dataPath = resolve(tierDir, `${key}.bin`)
  const metaPath = resolve(tierDir, `${key}.bin.meta.json`)

  const meta = readValidCacheMeta(metaPath, dataPath, tierConfig.ttlMs)
  if (meta) {
    logger.info(
      { bucketTier, cacheStatus: 'hit', objectPath: cleanObjectPath },
      'media_cache_lookup'
    )
    const parsedRange = parseByteRange(options?.rangeHeader, meta.size)
    if (options?.rangeHeader && !parsedRange) {
      throw createError({ statusCode: 416, statusMessage: 'Requested Range Not Satisfiable' })
    }
    if (parsedRange) {
      const length = parsedRange.end - parsedRange.start + 1
      return {
        statusCode: 206,
        contentType: meta.contentType,
        contentLength: length,
        contentRange: `bytes ${parsedRange.start}-${parsedRange.end}/${meta.size}`,
        acceptRanges: 'bytes',
        stream: createReadStream(dataPath, { start: parsedRange.start, end: parsedRange.end }),
        bucketTier,
        cacheStatus: 'hit',
      }
    }
    return {
      statusCode: 200,
      contentType: meta.contentType,
      contentLength: meta.size,
      acceptRanges: 'bytes',
      stream: createReadStream(dataPath),
      bucketTier,
      cacheStatus: 'hit',
    }
  }

  const upstream = await fetchMediaObject(
    `gs://${configs.mediaBucket}/${cleanObjectPath}`,
    idToken,
    {
      ...options,
      mediaBucket: configs.mediaBucket,
      mountedVolumePath: configs.mountedVolumePath,
      rangeHeader: options?.rangeHeader,
    }
  )

  const contentType = upstream.headers.get('content-type') || 'application/octet-stream'
  const rawLength = upstream.headers.get('content-length')
  const contentLength = rawLength ? Number.parseInt(rawLength, 10) : null
  const contentRange = upstream.headers.get('content-range') || undefined

  // Never cache partial 206 range slices or objects exceeding tier maxObjectBytes
  const isPartial = upstream.status === 206 || Boolean(contentRange)
  const tooLarge = contentLength !== null && contentLength > tierConfig.maxObjectBytes

  if (isPartial || tooLarge || !upstream.body) {
    logger.info(
      { bucketTier, cacheStatus: 'bypass', objectPath: cleanObjectPath },
      'media_cache_lookup'
    )
    if (!upstream.body) {
      throw createError({ statusCode: 502, statusMessage: 'Empty upstream media response body' })
    }
    return {
      statusCode: upstream.status === 206 ? 206 : 200,
      contentType,
      contentLength: Number.isFinite(contentLength) ? contentLength : null,
      ...(contentRange ? { contentRange } : {}),
      acceptRanges: 'bytes',
      stream: upstream.body,
      bucketTier,
      cacheStatus: 'bypass',
    }
  }

  const buffer = Buffer.from(await upstream.arrayBuffer())
  if (buffer.byteLength <= tierConfig.maxObjectBytes) {
    writeFileAtomic(dataPath, buffer)
    const nextMeta: CacheMeta = {
      contentType,
      size: buffer.byteLength,
      objectPath: cleanObjectPath,
    }
    writeFileAtomic(metaPath, JSON.stringify(nextMeta))
    evictTierCacheIfNeeded(tierDir, tierConfig.maxCacheBytes)
  }

  logger.info(
    { bucketTier, cacheStatus: 'miss', objectPath: cleanObjectPath },
    'media_cache_lookup'
  )
  return {
    statusCode: 200,
    contentType,
    contentLength: buffer.byteLength,
    acceptRanges: 'bytes',
    stream: Readable.from(buffer),
    bucketTier,
    cacheStatus: 'miss',
  }
}

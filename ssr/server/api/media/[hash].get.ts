import { resolve } from 'node:path'
import { createError, defineEventHandler, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import { serveMediaFromCache, type MediaVariant } from '../../services/media-cache.service'
import { getMediaDatabase } from '../../utils/file-database-cache'
import { getRuntimeDatabaseNames, parseSha1Param } from '../../utils/request-parsers'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'
import { getDefaultCacheDir } from '../../utils/storage-download'

export default defineEventHandler(async (event) => {
  const hash = parseSha1Param(event, 'hash', 'media')

  const query = getQuery(event)
  const rawVariant =
    typeof query.variant === 'string' ? query.variant.trim().toLowerCase() : 'thumbnail'
  if (rawVariant !== 'thumbnail' && rawVariant !== 'source') {
    throw createError({
      statusCode: 400,
      statusMessage: "Invalid variant parameter: expected 'thumbnail' or 'source'",
    })
  }
  const variant: MediaVariant = rawVariant

  const cfg = useRuntimeConfig(event)
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const dbNames = getRuntimeDatabaseNames(event)
  const snapshot = await getMediaDatabase(idToken, {
    ...storageOpts,
    dbFileName: dbNames.dbFileName,
  })

  const record = snapshot.recordsByHash[hash]
  if (!record) {
    throw createError({
      statusCode: 404,
      statusMessage: `Media record not found: ${hash}`,
    })
  }

  let gsUri: string
  if (variant === 'source') {
    gsUri = record.source_bucket_uri
  } else if (record.thumbnail_bucket_uri) {
    gsUri = record.thumbnail_bucket_uri
  } else if (record.file_type === 'IMAGE') {
    gsUri = record.source_bucket_uri
  } else {
    throw createError({
      statusCode: 404,
      statusMessage: `No thumbnail available for media ${hash}`,
    })
  }

  const mountedVolumePath = storageOpts.mountedVolumePath || getDefaultCacheDir()
  const dirName = cfg.mediaCache?.directoryName || 'media'
  const mediaCacheDir = resolve(mountedVolumePath, dirName)

  return await serveMediaFromCache(event, {
    hash,
    variant,
    gsUri,
    fileType: record.file_type,
    idToken,
    mediaCacheDir,
    maxCacheBytes: cfg.mediaCache?.maxCacheBytes || 2 * 1024 * 1024 * 1024,
    maxCacheableVideoBytes: cfg.mediaCache?.maxCacheableVideoBytes || 100 * 1024 * 1024,
    storageOptions: storageOpts,
  })
})

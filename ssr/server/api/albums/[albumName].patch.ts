import { createError, defineEventHandler, getRouterParam, readBody } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getEventLogger } from '../../services/logger.service'
import { updateAlbum } from '../../utils/albums-cache'
import { getMediaDatabase } from '../../utils/file-database-cache'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

export default defineEventHandler(async (event) => {
  const rawName = getRouterParam(event, 'albumName') || ''
  let decodedName: string
  try {
    decodedName = decodeURIComponent(rawName)
  } catch {
    throw createError({ statusCode: 400, statusMessage: 'Malformed albumName parameter' })
  }

  const cfg = useRuntimeConfig(event)
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const body = (await readBody(event)) as {
    newName?: unknown
    addHashes?: unknown
    removeHashes?: unknown
  } | null

  if (!body || typeof body !== 'object') {
    throw createError({
      statusCode: 400,
      statusMessage: 'Request body is required',
    })
  }

  const startedAt = Date.now()
  const snapshot = await getMediaDatabase(idToken, {
    ...storageOpts,
    dbFileName: cfg.database?.jsonFileName,
  }).catch(() => null)

  const result = await updateAlbum(
    decodedName,
    {
      newName: body.newName,
      addHashes: body.addHashes,
      removeHashes: body.removeHashes,
    },
    idToken,
    { ...storageOpts, albumsFileName: cfg.database?.albumsJsonFileName },
    snapshot
  )

  getEventLogger(event).info(
    {
      actorEmail: event.context.auth?.email,
      action: 'update',
      albumName: result.album?.name,
      hashCount: result.album?.totalFiles ?? 0,
      gcsGeneration: result.generation,
      durationMs: Date.now() - startedAt,
    },
    'album_mutated'
  )

  return {
    album: result.album,
  }
})

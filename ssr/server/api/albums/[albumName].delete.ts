import { createError, defineEventHandler, getRouterParam } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getEventLogger } from '../../services/logger.service'
import { deleteAlbum } from '../../utils/albums-cache'
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
  const startedAt = Date.now()

  const result = await deleteAlbum(decodedName, idToken, {
    ...storageOpts,
    albumsFileName: cfg.database?.albumsJsonFileName,
  })

  getEventLogger(event).info(
    {
      actorEmail: event.context.auth?.email,
      action: 'delete',
      albumName: result.deletedName,
      hashCount: 0,
      gcsGeneration: result.generation,
      durationMs: Date.now() - startedAt,
    },
    'album_mutated'
  )

  return {
    deleted: true,
    name: result.deletedName,
  }
})

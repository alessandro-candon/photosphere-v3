import { defineEventHandler } from 'h3'
import { getEventLogger } from '../../services/logger.service'
import { deleteAlbum } from '../../utils/albums-cache'
import { getRuntimeDatabaseNames, parseDecodedAlbumNameParam } from '../../utils/request-parsers'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

export default defineEventHandler(async (event) => {
  const decodedName = parseDecodedAlbumNameParam(event)
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const dbNames = getRuntimeDatabaseNames(event)
  const startedAt = Date.now()

  const result = await deleteAlbum(decodedName, idToken, {
    ...storageOpts,
    albumsFileName: dbNames.albumsFileName,
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

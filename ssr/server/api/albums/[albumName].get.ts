import { createError, defineEventHandler } from 'h3'
import { findAlbumIndexByName, getAlbums, toAlbumSummary } from '../../utils/albums-cache'
import { getMediaDatabase } from '../../utils/file-database-cache'
import { getRuntimeDatabaseNames, parseDecodedAlbumNameParam } from '../../utils/request-parsers'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

export default defineEventHandler(async (event) => {
  const decodedName = parseDecodedAlbumNameParam(event)
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const dbNames = getRuntimeDatabaseNames(event)

  const [albums, snapshot] = await Promise.all([
    getAlbums(idToken, { ...storageOpts, albumsFileName: dbNames.albumsFileName }),
    getMediaDatabase(idToken, { ...storageOpts, dbFileName: dbNames.dbFileName }),
  ])

  const idx = findAlbumIndexByName(albums, decodedName)
  if (idx === -1) {
    throw createError({
      statusCode: 404,
      statusMessage: `Album not found: ${decodedName}`,
    })
  }

  return toAlbumSummary(albums[idx]!, snapshot)
})

import { createError, defineEventHandler, getRouterParam } from 'h3'
import { useRuntimeConfig } from '#imports'
import { findAlbumIndexByName, getAlbums, toAlbumSummary } from '../../utils/albums-cache'
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

  const [albums, snapshot] = await Promise.all([
    getAlbums(idToken, { ...storageOpts, albumsFileName: cfg.database?.albumsJsonFileName }),
    getMediaDatabase(idToken, { ...storageOpts, dbFileName: cfg.database?.jsonFileName }),
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

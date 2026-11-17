import { createError, defineEventHandler, getRouterParam } from 'h3'
import { useRuntimeConfig } from '#imports'
import { deleteAlbum } from '../../utils/albums-cache'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

export default defineEventHandler(async (event) => {
  const cfg = useRuntimeConfig(event)
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const rawAlbumName = getRouterParam(event, 'albumName') || ''
  const albumName = decodeURIComponent(rawAlbumName).trim()
  if (!albumName) {
    throw createError({ statusCode: 400, statusMessage: 'Album name is required' })
  }

  await deleteAlbum(albumName, idToken, {
    ...storageOpts,
    albumsFileName: cfg.database?.albumsJsonFileName,
  })

  return { deleted: albumName }
})

import { createError, defineEventHandler, getRouterParam, readBody } from 'h3'
import { useRuntimeConfig } from '#imports'
import { updateAlbum } from '../../utils/albums-cache'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

interface UpdateAlbumBody {
  hashes?: unknown
}

export default defineEventHandler(async (event) => {
  const cfg = useRuntimeConfig(event)
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const rawAlbumName = getRouterParam(event, 'albumName') || ''
  const albumName = decodeURIComponent(rawAlbumName).trim()
  if (!albumName) {
    throw createError({ statusCode: 400, statusMessage: 'Album name is required' })
  }

  const body = await readBody<UpdateAlbumBody>(event)
  if (!body || !Array.isArray(body.hashes)) {
    throw createError({ statusCode: 400, statusMessage: 'hashes array is required' })
  }

  const album = await updateAlbum(albumName, body.hashes, idToken, {
    ...storageOpts,
    albumsFileName: cfg.database?.albumsJsonFileName,
  })

  return { album }
})

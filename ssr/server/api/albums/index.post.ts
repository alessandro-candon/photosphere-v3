import { createError, defineEventHandler, readBody, setResponseStatus } from 'h3'
import { useRuntimeConfig } from '#imports'
import { createAlbum } from '../../utils/albums-cache'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

interface CreateAlbumBody {
  name?: unknown
  hashes?: unknown
}

export default defineEventHandler(async (event) => {
  const cfg = useRuntimeConfig(event)
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const body = await readBody<CreateAlbumBody>(event)

  if (!body || typeof body.name !== 'string') {
    throw createError({ statusCode: 400, statusMessage: 'Album name is required' })
  }

  const album = await createAlbum(body.name, body.hashes ?? [], idToken, {
    ...storageOpts,
    albumsFileName: cfg.database?.albumsJsonFileName,
  })

  setResponseStatus(event, 201)
  return { album }
})

import { defineEventHandler } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getAlbums } from '../../utils/albums-cache'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

export default defineEventHandler(async (event) => {
  const cfg = useRuntimeConfig(event)
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)

  const albums = await getAlbums(idToken, {
    ...storageOpts,
    albumsFileName: cfg.database?.albumsJsonFileName,
  })

  return { albums }
})

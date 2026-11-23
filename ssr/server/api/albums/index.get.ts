import { defineEventHandler, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getAlbums, toAlbumSummary } from '../../utils/albums-cache'
import { getMediaDatabase } from '../../utils/file-database-cache'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

export default defineEventHandler(async (event) => {
  const cfg = useRuntimeConfig(event)
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const query = getQuery(event)

  const parsedPage = parseInt(String(query.page || '1'), 10)
  const page = Number.isFinite(parsedPage) && parsedPage >= 1 ? parsedPage : 1
  const parsedLimit = parseInt(String(query.limit || '20'), 10)
  const limit = Math.min(Math.max(Number.isFinite(parsedLimit) ? parsedLimit : 20, 1), 100)
  const skip = (page - 1) * limit

  const [albums, snapshot] = await Promise.all([
    getAlbums(idToken, { ...storageOpts, albumsFileName: cfg.database?.albumsJsonFileName }),
    getMediaDatabase(idToken, { ...storageOpts, dbFileName: cfg.database?.jsonFileName }),
  ])

  const totalCount = albums.length
  const paginated = albums.slice(skip, skip + limit)
  const items = paginated.map((album) => toAlbumSummary(album, snapshot))

  return {
    items,
    totalCount,
    page,
    limit,
    hasMore: skip + limit < totalCount,
  }
})

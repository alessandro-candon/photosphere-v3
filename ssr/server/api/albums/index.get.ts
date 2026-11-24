import { defineEventHandler, getQuery } from 'h3'
import { getAlbums, toAlbumSummary } from '../../utils/albums-cache'
import { getMediaDatabase } from '../../utils/file-database-cache'
import { getRuntimeDatabaseNames, parsePaginationParams } from '../../utils/request-parsers'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

export default defineEventHandler(async (event) => {
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const dbNames = getRuntimeDatabaseNames(event)
  const query = getQuery(event)

  const { page, limit, skip } = parsePaginationParams(query, 20, 100)

  const [albums, snapshot] = await Promise.all([
    getAlbums(idToken, { ...storageOpts, albumsFileName: dbNames.albumsFileName }),
    getMediaDatabase(idToken, { ...storageOpts, dbFileName: dbNames.dbFileName }),
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

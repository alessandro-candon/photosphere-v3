import { defineEventHandler, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import { assertAdminUser } from '../../services/auth.service'
import { getEventLogger } from '../../services/logger.service'
import { getAlbums, invalidateAlbumsCache } from '../../utils/albums-cache'
import {
  getLanguageDictionaries,
  getMediaDatabase,
  invalidateFileDatabaseCache,
  normalizeLanguageCode,
} from '../../utils/file-database-cache'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

export default defineEventHandler(async (event) => {
  const cfg = useRuntimeConfig(event)
  assertAdminUser(event.context.auth, cfg.auth?.adminEmail)

  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const query = getQuery(event)
  const lang = normalizeLanguageCode(query.lang, cfg.public?.defaultLang || 'en')

  invalidateFileDatabaseCache()
  invalidateAlbumsCache()

  const refreshOpts = { ...storageOpts, forceRefresh: true }
  const [snapshot, dicts, albums] = await Promise.all([
    getMediaDatabase(idToken, { ...refreshOpts, dbFileName: cfg.database?.jsonFileName }),
    getLanguageDictionaries(lang, idToken, {
      ...refreshOpts,
      labelsSuffix: cfg.database?.labelsJsonFileName,
      captionsSuffix: cfg.database?.captionsJsonFileName,
    }),
    getAlbums(idToken, { ...refreshOpts, albumsFileName: cfg.database?.albumsJsonFileName }),
  ])

  getEventLogger(event).info(
    {
      adminEmail: event.context.auth?.email,
      totalRecords: snapshot.sortedHashes.length,
      totalAlbums: albums.length,
      lang: dicts.lang,
    },
    'admin_database_refreshed'
  )

  return {
    refreshed: true,
    totalRecords: snapshot.sortedHashes.length,
    totalAlbums: albums.length,
    lang: dicts.lang,
    loadedAt: snapshot.loadedAt,
  }
})

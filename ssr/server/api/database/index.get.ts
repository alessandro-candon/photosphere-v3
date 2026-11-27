import { defineEventHandler, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import { assertAdminUser } from '../../services/auth.service'
import { getAlbums } from '../../utils/albums-cache'
import {
  getLanguageDictionaries,
  getMediaDatabase,
  normalizeLanguageCode,
} from '../../utils/file-database-cache'
import { getRuntimeDatabaseNames } from '../../utils/request-parsers'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

export default defineEventHandler(async (event) => {
  const cfg = useRuntimeConfig(event)
  assertAdminUser(event.context.auth, cfg.auth?.adminEmail)

  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const dbNames = getRuntimeDatabaseNames(event)
  const query = getQuery(event)
  const lang = normalizeLanguageCode(query.lang, cfg.public?.defaultLang || 'en')

  const [snapshot, dicts, albums] = await Promise.all([
    getMediaDatabase(idToken, { ...storageOpts, dbFileName: dbNames.dbFileName }),
    getLanguageDictionaries(lang, idToken, {
      ...storageOpts,
      labelsSuffix: dbNames.labelsSuffix,
      captionsSuffix: dbNames.captionsSuffix,
    }),
    getAlbums(idToken, { ...storageOpts, albumsFileName: dbNames.albumsFileName }),
  ])

  return {
    lang: dicts.lang,
    loadedAt: snapshot.loadedAt,
    files: {
      mediaDb: {
        fileName: dbNames.dbFileName,
        count: snapshot.sortedHashes.length,
        data: snapshot.recordsByHash,
      },
      labels: {
        fileName: `${dicts.lang}_${dbNames.labelsSuffix}`,
        count: Object.keys(dicts.labels).length,
        data: dicts.labels,
      },
      captions: {
        fileName: `${dicts.lang}_${dbNames.captionsSuffix}`,
        count: Object.keys(dicts.captions).length,
        data: dicts.captions,
      },
      albums: {
        fileName: dbNames.albumsFileName,
        count: albums.length,
        data: albums,
      },
    },
  }
})

import { defineEventHandler, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import { assertAdminUser } from '../../services/auth.service'
import { getAlbums } from '../../utils/albums-cache'
import {
  getLanguageDictionaries,
  getMediaDatabase,
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
  const dbFileName = cfg.database?.jsonFileName || 'photosphere_database_cloud.json'
  const labelsSuffix =
    cfg.database?.labelsJsonFileName || 'photosphere_image_labelling_database_cloud.json'
  const captionsSuffix =
    cfg.database?.captionsJsonFileName || 'photosphere_image_caption_database_cloud.json'
  const albumsFileName = cfg.database?.albumsJsonFileName || 'photosphere_albums.json'

  const [snapshot, dicts, albums] = await Promise.all([
    getMediaDatabase(idToken, { ...storageOpts, dbFileName }),
    getLanguageDictionaries(lang, idToken, {
      ...storageOpts,
      labelsSuffix,
      captionsSuffix,
    }),
    getAlbums(idToken, { ...storageOpts, albumsFileName }),
  ])

  return {
    lang: dicts.lang,
    loadedAt: snapshot.loadedAt,
    files: {
      mediaDb: {
        fileName: dbFileName,
        count: snapshot.sortedHashes.length,
        data: snapshot.recordsByHash,
      },
      labels: {
        fileName: `${dicts.lang}_${labelsSuffix}`,
        count: Object.keys(dicts.labels).length,
        data: dicts.labels,
      },
      captions: {
        fileName: `${dicts.lang}_${captionsSuffix}`,
        count: Object.keys(dicts.captions).length,
        data: dicts.captions,
      },
      albums: {
        fileName: albumsFileName,
        count: albums.length,
        data: albums,
      },
    },
  }
})

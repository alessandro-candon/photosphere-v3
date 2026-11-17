import { createError, defineEventHandler, getQuery, getRouterParam } from 'h3'
import { useRuntimeConfig } from '#imports'
import type { HydratedMediaItem } from '../../types/cache'
import { getAlbums } from '../../utils/albums-cache'
import {
  getLanguageDictionaries,
  getMediaDatabase,
  hydrateMediaRecord,
} from '../../utils/file-database-cache'
import { normalizeLanguageCode } from '../../utils/file-filters'
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

  const query = getQuery(event)
  const lang = normalizeLanguageCode(query.lang, cfg.public?.defaultLang || 'en')

  const [albums, snapshot, dicts] = await Promise.all([
    getAlbums(idToken, { ...storageOpts, albumsFileName: cfg.database?.albumsJsonFileName }),
    getMediaDatabase(idToken, { ...storageOpts, dbFileName: cfg.database?.jsonFileName }),
    getLanguageDictionaries(lang, idToken, {
      ...storageOpts,
      labelsSuffix: cfg.database?.labelsJsonFileName,
      captionsSuffix: cfg.database?.captionsJsonFileName,
    }),
  ])

  const album = albums.find((entry) => entry.name === albumName)
  if (!album) {
    throw createError({ statusCode: 404, statusMessage: `Album '${albumName}' not found` })
  }

  const mediaBucket = storageOpts.mediaBucket || ''
  const items: HydratedMediaItem[] = []
  for (const hash of album.hashes) {
    const rec = snapshot.recordsByHash[hash]
    if (rec) {
      items.push(hydrateMediaRecord(rec, dicts, mediaBucket))
    }
  }

  return {
    album,
    items,
    lang: dicts.lang,
  }
})

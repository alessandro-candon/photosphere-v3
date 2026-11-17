import { createError, defineEventHandler, getQuery, getRouterParam } from 'h3'
import { useRuntimeConfig } from '#imports'
import {
  getLanguageDictionaries,
  getMediaDatabase,
  hydrateMediaRecord,
} from '../../utils/file-database-cache'
import { normalizeLanguageCode } from '../../utils/file-filters'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

const SHA1_REGEX = /^[0-9a-f]{40}$/

export default defineEventHandler(async (event) => {
  const cfg = useRuntimeConfig(event)
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const hash = (getRouterParam(event, 'hash') || '').trim().toLowerCase()

  if (!SHA1_REGEX.test(hash)) {
    throw createError({ statusCode: 400, statusMessage: 'Invalid SHA-1 hash parameter' })
  }

  const query = getQuery(event)
  const lang = normalizeLanguageCode(query.lang, cfg.public?.defaultLang || 'en')

  const [snapshot, dicts] = await Promise.all([
    getMediaDatabase(idToken, { ...storageOpts, dbFileName: cfg.database?.jsonFileName }),
    getLanguageDictionaries(lang, idToken, {
      ...storageOpts,
      labelsSuffix: cfg.database?.labelsJsonFileName,
      captionsSuffix: cfg.database?.captionsJsonFileName,
    }),
  ])

  const record = snapshot.recordsByHash[hash]
  if (!record) {
    throw createError({ statusCode: 404, statusMessage: `Media record '${hash}' not found` })
  }

  return hydrateMediaRecord(record, dicts, storageOpts.mediaBucket || '')
})

import { createError, defineEventHandler, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import {
  getLanguageDictionaries,
  getMediaDatabase,
  normalizeLanguageCode,
} from '../../utils/file-database-cache'
import { toMediaDetail } from '../../utils/file-filters'
import { getRuntimeDatabaseNames, parseSha1Param } from '../../utils/request-parsers'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

export default defineEventHandler(async (event) => {
  const hash = parseSha1Param(event, 'hash', 'file')
  const cfg = useRuntimeConfig(event)
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const dbNames = getRuntimeDatabaseNames(event)
  const query = getQuery(event)
  const lang = normalizeLanguageCode(query.lang, cfg.public?.defaultLang || 'en')

  const [snapshot, dicts] = await Promise.all([
    getMediaDatabase(idToken, {
      ...storageOpts,
      dbFileName: dbNames.dbFileName,
    }),
    getLanguageDictionaries(lang, idToken, {
      ...storageOpts,
      labelsSuffix: dbNames.labelsSuffix,
      captionsSuffix: dbNames.captionsSuffix,
    }),
  ])

  const record = snapshot.recordsByHash[hash]
  if (!record) {
    throw createError({
      statusCode: 404,
      statusMessage: `File not found: ${hash}`,
    })
  }

  return toMediaDetail(record, dicts)
})

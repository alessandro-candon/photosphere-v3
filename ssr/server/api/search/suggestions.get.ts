import { defineEventHandler, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getLanguageDictionaries } from '../../utils/file-database-cache'
import { normalizeLanguageCode } from '../../utils/file-filters'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

export default defineEventHandler(async (event) => {
  const cfg = useRuntimeConfig(event)
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const query = getQuery(event)

  const lang = normalizeLanguageCode(query.lang, cfg.public?.defaultLang || 'en')
  const q = typeof query.q === 'string' ? query.q.trim().toLowerCase() : ''
  const limitRaw = Number.parseInt(String(query.limit ?? '25'), 10)
  const limit = Number.isFinite(limitRaw) && limitRaw > 0 ? Math.min(limitRaw, 100) : 25

  const dicts = await getLanguageDictionaries(lang, idToken, {
    ...storageOpts,
    labelsSuffix: cfg.database?.labelsJsonFileName,
    captionsSuffix: cfg.database?.captionsJsonFileName,
  })

  const filterValues = (values: string[]): string[] => {
    const unique = Array.from(new Set(values))
    const matched = q ? unique.filter((v) => v.toLowerCase().includes(q)) : unique
    return matched.slice(0, limit)
  }

  return {
    lang: dicts.lang,
    labels: filterValues(Object.values(dicts.labels)),
    captions: filterValues(Object.values(dicts.captions)),
  }
})

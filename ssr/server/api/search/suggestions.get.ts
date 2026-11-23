import { createError, defineEventHandler, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import { getLanguageDictionaries, normalizeLanguageCode } from '../../utils/file-database-cache'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

export interface SearchSuggestionItem {
  text: string
  kind: 'label' | 'caption'
  index: number
}

const parseFieldParam = (raw: unknown): 'labels' | 'captions' | undefined => {
  if (typeof raw !== 'string' || !raw.trim()) {
    return undefined
  }
  const clean = raw.trim().toLowerCase()
  if (clean === 'labels' || clean === 'tags') {
    return 'labels'
  }
  if (clean === 'captions') {
    return 'captions'
  }
  throw createError({
    statusCode: 400,
    statusMessage: "Bad Request: field must be 'labels', 'tags', or 'captions'",
  })
}

export default defineEventHandler(async (event) => {
  const query = getQuery(event)
  const field = parseFieldParam(query.field)
  const rawQ = typeof query.q === 'string' ? query.q.trim() : ''
  if (!rawQ) {
    return { suggestions: [] as SearchSuggestionItem[] }
  }

  const parsedLimit = parseInt(String(query.limit || '10'), 10)
  const limit = Math.min(Math.max(Number.isFinite(parsedLimit) ? parsedLimit : 10, 1), 25)

  const cfg = useRuntimeConfig(event)
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const lang = normalizeLanguageCode(query.lang, cfg.public?.defaultLang || 'en')

  const dicts = await getLanguageDictionaries(lang, idToken, {
    ...storageOpts,
    labelsSuffix: cfg.database?.labelsJsonFileName,
    captionsSuffix: cfg.database?.captionsJsonFileName,
  })

  const needle = rawQ.toLowerCase()
  const prefixMatches: SearchSuggestionItem[] = []
  const substringMatches: SearchSuggestionItem[] = []
  const seenText = new Set<string>()

  const collectFromDict = (dict: Record<string, string>, kind: 'label' | 'caption') => {
    for (const [rawIdx, text] of Object.entries(dict)) {
      const lower = text.toLowerCase()
      if (!lower.includes(needle)) continue
      const dedupeKey = `${kind}:${lower}`
      if (seenText.has(dedupeKey)) continue
      seenText.add(dedupeKey)

      const entry: SearchSuggestionItem = {
        text,
        kind,
        index: Number(rawIdx),
      }
      if (lower.startsWith(needle)) {
        prefixMatches.push(entry)
      } else {
        substringMatches.push(entry)
      }
    }
  }

  if (!field || field === 'labels') {
    collectFromDict(dicts.labels, 'label')
  }
  if (!field || field === 'captions') {
    collectFromDict(dicts.captions, 'caption')
  }

  return {
    suggestions: [...prefixMatches, ...substringMatches].slice(0, limit),
  }
})

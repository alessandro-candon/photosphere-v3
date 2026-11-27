import { defineEventHandler, getQuery } from 'h3'
import { useRuntimeConfig } from '#imports'
import type { SearchSuggestion } from '#shared/types'
import { getLanguageDictionaries, normalizeLanguageCode } from '../../utils/file-database-cache'
import {
  getRuntimeDatabaseNames,
  parsePaginationParams,
  parseSearchFieldParam,
} from '../../utils/request-parsers'
import { getRuntimeStorageOptions, requireBearerToken } from '../../utils/runtime-storage'

export type SearchSuggestionItem = SearchSuggestion

export default defineEventHandler(async (event) => {
  const query = getQuery(event)
  const field = parseSearchFieldParam(query.field, 'field')
  const rawQ = typeof query.q === 'string' ? query.q.trim() : ''
  if (!rawQ) {
    return { suggestions: [] as SearchSuggestionItem[] }
  }

  const { limit } = parsePaginationParams(query, 10, 25)
  const cfg = useRuntimeConfig(event)
  const idToken = requireBearerToken(event)
  const storageOpts = getRuntimeStorageOptions(event)
  const dbNames = getRuntimeDatabaseNames(event)
  const lang = normalizeLanguageCode(query.lang, cfg.public?.defaultLang || 'en')

  const dicts = await getLanguageDictionaries(lang, idToken, {
    ...storageOpts,
    labelsSuffix: dbNames.labelsSuffix,
    captionsSuffix: dbNames.captionsSuffix,
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

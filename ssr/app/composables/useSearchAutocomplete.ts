import { ref } from 'vue'
import type { LocationSearchResult, SearchFieldMode, SearchSuggestion } from '../types'
import { usePhotosphereApi } from './usePhotosphereApi'

export const useSearchAutocomplete = () => {
  const { fetchSearchSuggestions, searchLocations } = usePhotosphereApi()

  const suggestions = ref<SearchSuggestion[]>([])
  const locationResults = ref<LocationSearchResult[]>([])
  const locationLoading = ref(false)
  const locationError = ref('')

  const handleSuggestionQuery = async ({ q, field }: { q: string; field: SearchFieldMode }) => {
    if (!q.trim()) {
      suggestions.value = []
      return
    }
    try {
      suggestions.value = await fetchSearchSuggestions(q, field, 10)
    } catch {
      suggestions.value = []
    }
  }

  const handleLocationSearch = async (q: string) => {
    locationLoading.value = true
    locationError.value = ''
    try {
      locationResults.value = await searchLocations(q)
    } catch (error) {
      locationResults.value = []
      locationError.value =
        error instanceof Error ? error.message : 'Failed to search location via OpenStreetMap'
    } finally {
      locationLoading.value = false
    }
  }

  return {
    suggestions,
    locationResults,
    locationLoading,
    locationError,
    handleSuggestionQuery,
    handleLocationSearch,
  }
}

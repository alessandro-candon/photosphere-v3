import type { Auth } from 'firebase/auth'
import { storeToRefs } from 'pinia'
import { useNuxtApp } from '#imports'
import { API_ENDPOINTS } from '../constants/api'
import { useAuthStore } from '../stores/auth'
import type {
  AlbumSummary,
  DatabaseSnapshotResponse,
  GalleryFilters,
  HeatmapApiResponse,
  HeatmapQueryParams,
  LocationSearchResult,
  MediaDetail,
  MediaGridItem,
  MediaSortOrder,
  PaginatedResponse,
  RefreshDatabaseResponse,
  SearchFieldMode,
  SearchSuggestion,
  UserCapabilities,
} from '../types'

export class PhotosphereApiError extends Error {
  statusCode: number
  requestId?: string

  constructor(message: string, statusCode: number, requestId?: string) {
    super(message)
    this.name = 'PhotosphereApiError'
    this.statusCode = statusCode
    this.requestId = requestId
  }
}

const extractErrorMessage = async (response: Response): Promise<string> => {
  try {
    const payload = (await response.json()) as { statusMessage?: string; message?: string }
    if (payload.statusMessage) return payload.statusMessage
    if (payload.message) return payload.message
  } catch {
    // Fallback to HTTP status text
  }
  return response.statusText || `Request failed (${response.status})`
}

export const usePhotosphereApi = () => {
  const nuxtApp = useNuxtApp()
  const authStore = useAuthStore()
  const { idToken, preferredLang } = storeToRefs(authStore)

  const syncMediaSession = async (tokenOverride?: string): Promise<void> => {
    const token = tokenOverride || idToken.value
    if (!token) return
    await fetch(API_ENDPOINTS.authSession, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      credentials: 'same-origin',
    })
  }

  const clearMediaSession = async (): Promise<void> => {
    await fetch(API_ENDPOINTS.authSession, {
      method: 'DELETE',
      credentials: 'same-origin',
    })
  }

  const requestJson = async <T>(
    url: string,
    init: RequestInit = {},
    allowRefreshRetry = true
  ): Promise<T> => {
    const headers = new Headers(init.headers)
    if (!headers.has('Authorization') && idToken.value) {
      headers.set('Authorization', `Bearer ${idToken.value}`)
    }

    const response = await fetch(url, {
      ...init,
      headers,
      credentials: 'same-origin',
    })

    if (response.status === 401 && allowRefreshRetry) {
      const firebaseAuth = (nuxtApp.$firebaseAuth as Auth | null | undefined) || null
      if (firebaseAuth?.currentUser) {
        try {
          const freshToken = await firebaseAuth.currentUser.getIdToken(true)
          authStore.setSession(authStore.user, freshToken)
          await syncMediaSession(freshToken).catch(() => {})
          const retryHeaders = new Headers(init.headers)
          retryHeaders.set('Authorization', `Bearer ${freshToken}`)
          return await requestJson<T>(url, { ...init, headers: retryHeaders }, false)
        } catch {
          // Fall through to error extraction
        }
      }
    }

    if (!response.ok) {
      const requestId = response.headers.get('x-request-id') || undefined
      const message = await extractErrorMessage(response)
      throw new PhotosphereApiError(message, response.status, requestId)
    }

    return (await response.json()) as T
  }

  const fetchMe = async (tokenOverride?: string): Promise<UserCapabilities> => {
    const headers = tokenOverride ? { Authorization: `Bearer ${tokenOverride}` } : undefined
    return await requestJson<UserCapabilities>(API_ENDPOINTS.me, { headers }, !tokenOverride)
  }

  const bootstrapSession = async (token: string): Promise<void> => {
    await syncMediaSession(token)
    const caps = await fetchMe(token)
    authStore.setCapabilities({
      isAdmin: caps.isAdmin,
      canEditAlbums: caps.canEditAlbums,
    })
  }

  const listFiles = async (
    filters: GalleryFilters = {},
    page = 1,
    limit = 50,
    options: { sort?: MediaSortOrder; signal?: AbortSignal } = {}
  ): Promise<PaginatedResponse<MediaGridItem>> => {
    const params = new URLSearchParams({
      page: String(page),
      limit: String(limit),
      lang: preferredLang.value,
    })
    if (options.sort) params.set('sort', options.sort)
    if (filters.q) params.set('q', filters.q)
    if (filters.searchField) params.set('searchField', filters.searchField)
    if (filters.labelIndex !== undefined) params.set('labelIndex', String(filters.labelIndex))
    if (filters.captionIndex !== undefined) params.set('captionIndex', String(filters.captionIndex))
    if (filters.fileType) params.set('fileType', filters.fileType)
    if (filters.dateFrom) params.set('dateFrom', filters.dateFrom)
    if (filters.dateTo) params.set('dateTo', filters.dateTo)
    if (filters.memoryDate) params.set('memoryDate', filters.memoryDate)
    if (filters.album) params.set('album', filters.album)
    if (filters.notInAlbum) params.set('notInAlbum', 'true')
    if (filters.lat !== undefined && filters.lng !== undefined) {
      params.set('lat', String(filters.lat))
      params.set('lng', String(filters.lng))
      if (filters.radiusKm !== undefined) {
        params.set('radiusKm', String(filters.radiusKm))
      }
    }
    return await requestJson<PaginatedResponse<MediaGridItem>>(`${API_ENDPOINTS.files}?${params}`, {
      signal: options.signal,
    })
  }

  const fetchHeatmapClusters = async (
    queryParams: HeatmapQueryParams,
    filters: GalleryFilters = {},
    signal?: AbortSignal
  ): Promise<HeatmapApiResponse> => {
    const params = new URLSearchParams({
      north: String(queryParams.north),
      south: String(queryParams.south),
      east: String(queryParams.east),
      west: String(queryParams.west),
      zoom: String(queryParams.zoom),
      mode: queryParams.mode,
      lang: preferredLang.value,
    })
    if (filters.q) params.set('q', filters.q)
    if (filters.searchField) params.set('searchField', filters.searchField)
    if (filters.labelIndex !== undefined) params.set('labelIndex', String(filters.labelIndex))
    if (filters.captionIndex !== undefined) params.set('captionIndex', String(filters.captionIndex))
    if (filters.fileType) params.set('fileType', filters.fileType)
    if (filters.dateFrom) params.set('dateFrom', filters.dateFrom)
    if (filters.dateTo) params.set('dateTo', filters.dateTo)
    if (filters.memoryDate) params.set('memoryDate', filters.memoryDate)
    if (filters.album) params.set('album', filters.album)
    if (filters.notInAlbum) params.set('notInAlbum', 'true')

    return await requestJson<HeatmapApiResponse>(`${API_ENDPOINTS.mapHeatmap}?${params}`, {
      signal,
    })
  }

  const getFileDetail = async (hash: string): Promise<MediaDetail> => {
    const params = new URLSearchParams({ lang: preferredLang.value })
    return await requestJson<MediaDetail>(
      `${API_ENDPOINTS.files}/${encodeURIComponent(hash)}?${params}`
    )
  }

  const fetchSearchSuggestions = async (
    q: string,
    field: SearchFieldMode = 'labels',
    limit = 10
  ): Promise<SearchSuggestion[]> => {
    const clean = q.trim()
    if (!clean) return []
    const params = new URLSearchParams({
      q: clean,
      field,
      lang: preferredLang.value,
      limit: String(limit),
    })
    const res = await requestJson<{ suggestions: SearchSuggestion[] }>(
      `${API_ENDPOINTS.searchSuggestions}?${params}`
    )
    return res.suggestions
  }

  const searchLocations = async (q: string): Promise<LocationSearchResult[]> => {
    const clean = q.trim()
    if (clean.length < 2) return []
    const params = new URLSearchParams({ q: clean })
    const res = await requestJson<{ results: LocationSearchResult[] }>(
      `${API_ENDPOINTS.locationSearch}?${params}`
    )
    return res.results
  }

  const listAlbums = async (page = 1, limit = 20): Promise<PaginatedResponse<AlbumSummary>> => {
    const params = new URLSearchParams({
      page: String(page),
      limit: String(limit),
    })
    return await requestJson<PaginatedResponse<AlbumSummary>>(`${API_ENDPOINTS.albums}?${params}`)
  }

  const getAlbum = async (albumName: string): Promise<AlbumSummary> => {
    return await requestJson<AlbumSummary>(
      `${API_ENDPOINTS.albums}/${encodeURIComponent(albumName)}`
    )
  }

  const createAlbum = async (
    name: string,
    hashes: string[] = []
  ): Promise<{ album: AlbumSummary }> => {
    return await requestJson<{ album: AlbumSummary }>(API_ENDPOINTS.albums, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, hashes }),
    })
  }

  const updateAlbum = async (
    albumName: string,
    patch: { newName?: string; addHashes?: string[]; removeHashes?: string[] }
  ): Promise<{ album: AlbumSummary }> => {
    return await requestJson<{ album: AlbumSummary }>(
      `${API_ENDPOINTS.albums}/${encodeURIComponent(albumName)}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      }
    )
  }

  const deleteAlbum = async (albumName: string): Promise<{ deleted: boolean; name: string }> => {
    return await requestJson<{ deleted: boolean; name: string }>(
      `${API_ENDPOINTS.albums}/${encodeURIComponent(albumName)}`,
      {
        method: 'DELETE',
      }
    )
  }

  const fetchDatabase = async (): Promise<DatabaseSnapshotResponse> => {
    const params = new URLSearchParams({ lang: preferredLang.value })
    return await requestJson<DatabaseSnapshotResponse>(`${API_ENDPOINTS.database}?${params}`)
  }

  const refreshDatabase = async (): Promise<RefreshDatabaseResponse> => {
    const params = new URLSearchParams({ lang: preferredLang.value })
    return await requestJson<RefreshDatabaseResponse>(
      `${API_ENDPOINTS.refreshDatabase}?${params}`,
      {
        method: 'POST',
      }
    )
  }

  return {
    requestJson,
    syncMediaSession,
    clearMediaSession,
    fetchMe,
    bootstrapSession,
    listFiles,
    fetchHeatmapClusters,
    getFileDetail,
    fetchSearchSuggestions,
    searchLocations,
    listAlbums,
    getAlbum,
    createAlbum,
    updateAlbum,
    deleteAlbum,
    fetchDatabase,
    refreshDatabase,
  }
}

import axios, { type AxiosInstance } from 'axios'
import { storeToRefs } from 'pinia'
import { API_ENDPOINTS } from '../constants/api'
import { useAuthStore } from '../stores/auth'
import type {
  AlbumDetailResponse,
  AlbumMutationResponse,
  AlbumsListResponse,
  LocationSearchResponse,
  MediaFilterState,
  MediaItem,
  PaginatedFilesResponse,
  RefreshDatabaseResponse,
  SuggestionsResponse,
} from '../types'

export const usePhotosphereApi = () => {
  const authStore = useAuthStore()
  const { idToken, preferredLang } = storeToRefs(authStore)

  const client: AxiosInstance = axios.create()

  client.interceptors.request.use((config) => {
    if (idToken.value) {
      config.headers.Authorization = `Bearer ${idToken.value}`
    }
    return config
  })

  const fetchFiles = async (
    filters: Partial<MediaFilterState> & { page?: number; limit?: number } = {}
  ): Promise<PaginatedFilesResponse> => {
    const params: Record<string, string | number | boolean> = {
      lang: preferredLang.value,
      page: filters.page ?? 1,
      limit: filters.limit ?? 60,
    }
    if (filters.q) params.q = filters.q
    if (filters.fileType && filters.fileType !== 'ALL') params.fileType = filters.fileType
    if (filters.album) params.album = filters.album
    if (filters.hasLocation) params.hasLocation = true
    if (filters.dateFrom) params.dateFrom = Math.floor(new Date(filters.dateFrom).getTime() / 1000)
    if (filters.dateTo) params.dateTo = Math.floor(new Date(filters.dateTo).getTime() / 1000)

    const { data } = await client.get<PaginatedFilesResponse>(API_ENDPOINTS.files, { params })
    return data
  }

  const fetchFileByHash = async (hash: string): Promise<MediaItem> => {
    const { data } = await client.get<MediaItem>(`${API_ENDPOINTS.files}/${hash}`, {
      params: { lang: preferredLang.value },
    })
    return data
  }

  const fetchSuggestions = async (q = ''): Promise<SuggestionsResponse> => {
    const { data } = await client.get<SuggestionsResponse>(API_ENDPOINTS.searchSuggestions, {
      params: { q, lang: preferredLang.value },
    })
    return data
  }

  const searchLocation = async (q: string): Promise<LocationSearchResponse> => {
    const { data } = await client.get<LocationSearchResponse>(API_ENDPOINTS.locationSearch, {
      params: { q },
    })
    return data
  }

  const fetchAlbums = async (): Promise<AlbumsListResponse> => {
    const { data } = await client.get<AlbumsListResponse>(API_ENDPOINTS.albums)
    return data
  }

  const fetchAlbumDetail = async (albumName: string): Promise<AlbumDetailResponse> => {
    const { data } = await client.get<AlbumDetailResponse>(
      `${API_ENDPOINTS.albums}/${encodeURIComponent(albumName)}`,
      { params: { lang: preferredLang.value } }
    )
    return data
  }

  const createAlbum = async (name: string, hashes: string[]): Promise<AlbumMutationResponse> => {
    const { data } = await client.post<AlbumMutationResponse>(API_ENDPOINTS.albums, {
      name,
      hashes,
    })
    return data
  }

  const updateAlbum = async (
    albumName: string,
    hashes: string[]
  ): Promise<AlbumMutationResponse> => {
    const { data } = await client.put<AlbumMutationResponse>(
      `${API_ENDPOINTS.albums}/${encodeURIComponent(albumName)}`,
      { hashes }
    )
    return data
  }

  const deleteAlbum = async (albumName: string): Promise<void> => {
    await client.delete(`${API_ENDPOINTS.albums}/${encodeURIComponent(albumName)}`)
  }

  const refreshDatabase = async (): Promise<RefreshDatabaseResponse> => {
    const { data } = await client.post<RefreshDatabaseResponse>(
      API_ENDPOINTS.refreshDatabase,
      null,
      { params: { lang: preferredLang.value } }
    )
    return data
  }

  const fetchMediaAsBlob = async (proxyUrl: string, signal?: AbortSignal): Promise<string> => {
    const { data } = await client.get<Blob>(proxyUrl, {
      responseType: 'blob',
      signal,
    })
    return URL.createObjectURL(data)
  }

  // Stream progressive chunks with HTTP Range instead of buffering entire videos upfront
  const streamVideoObjectUrl = async (proxyUrl: string, signal?: AbortSignal): Promise<string> => {
    const headers: Record<string, string> = {}
    if (idToken.value) {
      headers.Authorization = `Bearer ${idToken.value}`
    }
    const response = await fetch(proxyUrl, { headers, signal })
    if (!response.ok || !response.body) {
      throw new Error(`Video stream failed (${response.status})`)
    }
    const blob = await response.blob()
    return URL.createObjectURL(blob)
  }

  return {
    fetchFiles,
    fetchFileByHash,
    fetchSuggestions,
    searchLocation,
    fetchAlbums,
    fetchAlbumDetail,
    createAlbum,
    updateAlbum,
    deleteAlbum,
    refreshDatabase,
    fetchMediaAsBlob,
    streamVideoObjectUrl,
  }
}

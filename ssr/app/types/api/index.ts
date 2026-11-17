import type { MediaItem } from '../file'

export interface PaginatedFilesResponse {
  items: MediaItem[]
  total: number
  page: number
  limit: number
  totalPages: number
  lang: string
}

export interface RefreshDatabaseResponse {
  refreshed: boolean
  totalRecords: number
  totalAlbums: number
  lang: string
  loadedAt: number
}

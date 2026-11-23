export * from '../media'

export type MediaFileType = 'FILE' | 'IMAGE' | 'VIDEO'

export interface RawMediaRecord {
  hash: string
  average_hash: string | null
  source_bucket_uri: string
  thumbnail_bucket_uri: string | null
  file_type: MediaFileType
  created_at: string | null
  created_at_timestamp: number | null
  latitude: number | null
  longitude: number | null
  geohash: string | null
  label_indexes: number[]
  caption_index: number | null
}

export type KeyValueDictionary = Record<string, string>

export interface AlbumRecord {
  name: string
  hashes: string[]
}

export interface DatabaseFilePayload<T> {
  fileName: string
  count: number
  data: T
}

export interface DatabaseSnapshotResponse {
  lang: string
  loadedAt: number
  files: {
    mediaDb: DatabaseFilePayload<Record<string, RawMediaRecord>>
    labels: DatabaseFilePayload<KeyValueDictionary>
    captions: DatabaseFilePayload<KeyValueDictionary>
    albums: DatabaseFilePayload<AlbumRecord[]>
  }
}

export interface RefreshDatabaseResponse {
  refreshed: boolean
  totalRecords: number
  totalAlbums: number
  lang: string
  loadedAt: number
}

export interface UserCapabilities {
  email: string
  isAdmin: boolean
  canEditAlbums: boolean
}

export interface PaginatedResponse<T> {
  items: T[]
  totalCount: number
  page: number
  limit: number
  hasMore: boolean
}

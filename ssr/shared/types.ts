import type {
  BasemapStyle,
  GeohashPrecision,
  HeatmapDataMode,
  HeatmapPointTuple,
  MediaFileType,
  MediaSortOrder,
  SearchFieldMode,
} from './constants'

export type {
  BasemapStyle,
  GeohashPrecision,
  HeatmapDataMode,
  HeatmapPointTuple,
  MediaFileType,
  MediaSortOrder,
  SearchFieldMode,
}

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

export interface MediaGridItem {
  hash: string
  fileType: MediaFileType
  createdAt: string | null
  createdAtTimestamp: number | null
  fileName: string
  hasThumbnail: boolean
  thumbnailUrl: string | null
  sourceUrl: string
  latitude: number | null
  longitude: number | null
  geohash: string | null
  distanceKm?: number | null
}

export interface MediaDetail extends MediaGridItem {
  labels: string[]
  caption: string | null
}

export interface AlbumSummary {
  name: string
  totalFiles: number
  coverThumbnails: string[]
}

export interface GalleryFilters {
  q?: string
  searchField?: SearchFieldMode
  labelIndex?: number
  captionIndex?: number
  fileType?: MediaFileType
  dateFrom?: string
  dateTo?: string
  memoryDate?: string
  album?: string
  notInAlbum?: boolean
  lat?: number
  lng?: number
  radiusKm?: number
  place?: string
}

export interface HeatmapQueryParams {
  north: number
  south: number
  east: number
  west: number
  zoom: number
  mode: HeatmapDataMode
}

export interface HeatmapApiResponse {
  points: HeatmapPointTuple[]
  precision: GeohashPrecision
  requestedMode: HeatmapDataMode
  effectiveMode: HeatmapDataMode
  fallbackTriggered: boolean
  viewportPointCount: number
  totalGeolocatedCount: number
  maxBucketCount: number
}

export interface WorldHeatmapSettings {
  basemap: BasemapStyle
  dataMode: HeatmapDataMode
  dynamicRadius: boolean
  baseRadius: number
  blur: number
  maxIntensity: number
  maxInspectResults: number
}

export interface SearchSuggestion {
  text: string
  kind: 'label' | 'caption'
  index: number
}

export interface LocationSearchResult {
  placeId: string
  displayName: string
  lat: number
  lng: number
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

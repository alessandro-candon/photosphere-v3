import type { MediaFileType } from './api'

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

export type MediaSortOrder = 'date' | 'distance'
export type BasemapStyle = 'dark' | 'light' | 'satellite'
export type HeatmapDataMode = 'geohash' | 'raw'
export type HeatmapPointTuple = [number, number, number]

export interface WorldHeatmapSettings {
  basemap: BasemapStyle
  dataMode: HeatmapDataMode
  dynamicRadius: boolean
  baseRadius: number
  blur: number
  maxIntensity: number
  maxInspectResults: number
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
  precision: 2 | 3 | 4 | 5 | 6
  requestedMode: HeatmapDataMode
  effectiveMode: HeatmapDataMode
  fallbackTriggered: boolean
  viewportPointCount: number
  totalGeolocatedCount: number
  maxBucketCount: number
}

export type SearchFieldMode = 'labels' | 'captions'

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

export interface AlbumSummary {
  name: string
  totalFiles: number
  coverThumbnails: string[]
}

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
}

export interface MediaDetail extends MediaGridItem {
  latitude: number | null
  longitude: number | null
  geohash: string | null
  labels: string[]
  caption: string | null
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

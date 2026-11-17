export type MediaFileType = 'FILE' | 'IMAGE' | 'VIDEO'

export interface ProxyUrls {
  sourceUrl: string
  thumbnailUrl: string | null
}

export interface MediaItem {
  hash: string
  averageHash: string | null
  fileType: MediaFileType
  createdAt: string | null
  createdAtTimestamp: number | null
  latitude: number | null
  longitude: number | null
  geohash: string | null
  labels: string[]
  caption: string | null
  proxyUrls: ProxyUrls
}

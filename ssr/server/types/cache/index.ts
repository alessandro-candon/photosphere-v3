export type MediaFileType = 'FILE' | 'IMAGE' | 'VIDEO'

export type BucketTier = 'thumbnail' | 'media'

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

export interface ProxyUrls {
  sourceUrl: string
  thumbnailUrl: string | null
}

export interface HydratedMediaItem {
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

export interface CacheTierConfig {
  directoryName: string
  ttlMs: number
  maxObjectBytes: number
  maxCacheBytes: number
}

export interface MediaDatabaseSnapshot {
  recordsByHash: Record<string, RawMediaRecord>
  sortedHashes: string[]
  loadedAt: number
}

export interface LanguageDictionaries {
  lang: string
  labels: KeyValueDictionary
  captions: KeyValueDictionary
  loadedAt: number
}

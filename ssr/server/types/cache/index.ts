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

export interface MediaDatabaseSnapshot {
  recordsByHash: Record<string, RawMediaRecord>
  sortedHashes: string[]
  byMonthDay: Record<string, string[]>
  byLabelIndex: Record<number, string[]>
  loadedAt: number
}

export interface LanguageDictionaries {
  lang: string
  labels: KeyValueDictionary
  captions: KeyValueDictionary
  loadedAt: number
}

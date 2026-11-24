import type {
  AlbumRecord,
  GeohashPrecision,
  KeyValueDictionary,
  MediaFileType,
  RawMediaRecord,
} from '#shared/index'

export type { AlbumRecord, GeohashPrecision, KeyValueDictionary, MediaFileType, RawMediaRecord }

export interface GeohashClusterBucket {
  prefix: string
  count: number
  avgLat: number
  avgLng: number
}

export interface MediaDatabaseSnapshot {
  recordsByHash: Record<string, RawMediaRecord>
  sortedHashes: string[]
  byMonthDay: Record<string, string[]>
  byLabelIndex: Record<number, string[]>
  byCaptionIndex: Record<number, string[]>
  geolocatedHashes: string[]
  unfilteredGeohashBuckets: Record<GeohashPrecision, GeohashClusterBucket[]>
  loadedAt: number
}

export interface LanguageDictionaries {
  lang: string
  labels: KeyValueDictionary
  captions: KeyValueDictionary
  loadedAt: number
}

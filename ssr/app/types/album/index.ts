import type { MediaItem } from '../file'

export interface AlbumRecord {
  name: string
  hashes: string[]
}

export interface AlbumsListResponse {
  albums: AlbumRecord[]
}

export interface AlbumMutationResponse {
  album: AlbumRecord
}

export interface AlbumDetailResponse {
  album: AlbumRecord
  items: MediaItem[]
  lang: string
}

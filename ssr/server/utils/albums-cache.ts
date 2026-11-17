import { resolve } from 'node:path'
import { createError } from 'h3'
import type { AlbumRecord } from '../types/cache'
import {
  ensureMountedVolumeDir,
  loadJsonDatabase,
  uploadDataFile,
  writeFileAtomic,
  type StorageOptions,
} from './storage-download'

const SHA1_REGEX = /^[0-9a-f]{40}$/
const ALBUMS_FILENAME = 'photosphere_albums.json'

let albumsCache: AlbumRecord[] | null = null

export const invalidateAlbumsCache = (): void => {
  albumsCache = null
}

export const normalizeHashes = (hashes: unknown): string[] => {
  if (!Array.isArray(hashes)) {
    throw createError({
      statusCode: 400,
      statusMessage: 'hashes must be an array of SHA-1 digests',
    })
  }
  const seen = new Set<string>()
  const clean: string[] = []
  for (const item of hashes) {
    if (typeof item !== 'string' || !SHA1_REGEX.test(item)) {
      throw createError({
        statusCode: 400,
        statusMessage: `Invalid SHA-1 digest in album hashes: '${String(item)}'`,
      })
    }
    if (!seen.has(item)) {
      seen.add(item)
      clean.push(item)
    }
  }
  return clean
}

export const validateAlbumsPayload = (raw: unknown): AlbumRecord[] => {
  if (!Array.isArray(raw)) {
    throw createError({
      statusCode: 500,
      statusMessage: 'Invalid photosphere_albums.json: expected array of album objects',
    })
  }
  return raw.map((entry, idx) => {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
      throw createError({
        statusCode: 500,
        statusMessage: `Invalid album entry at index ${idx}`,
      })
    }
    const obj = entry as Record<string, unknown>
    if (typeof obj.name !== 'string' || obj.name.trim().length === 0) {
      throw createError({
        statusCode: 500,
        statusMessage: `Invalid album name at index ${idx}`,
      })
    }
    const hashes = normalizeHashes(obj.hashes)
    return { name: obj.name.trim(), hashes }
  })
}

export const getAlbums = async (
  idToken: string,
  options?: StorageOptions & { albumsFileName?: string }
): Promise<AlbumRecord[]> => {
  if (albumsCache && !options?.forceRefresh) {
    return albumsCache
  }
  const fileName = options?.albumsFileName || ALBUMS_FILENAME
  try {
    const loaded = await loadJsonDatabase(
      fileName,
      fileName,
      idToken,
      validateAlbumsPayload,
      options
    )
    albumsCache = loaded
    return loaded
  } catch (error) {
    if ((error as { statusCode?: number }).statusCode === 404) {
      albumsCache = []
      return []
    }
    throw error
  }
}

const persistAlbums = async (
  albums: AlbumRecord[],
  idToken: string,
  options?: StorageOptions & { albumsFileName?: string }
): Promise<AlbumRecord[]> => {
  const fileName = options?.albumsFileName || ALBUMS_FILENAME
  const serialized = JSON.stringify(albums)
  await uploadDataFile(fileName, serialized, idToken, options)
  const dir = ensureMountedVolumeDir(undefined, options?.mountedVolumePath)
  writeFileAtomic(resolve(dir, fileName), serialized)
  albumsCache = albums
  return albums
}

export const createAlbum = async (
  name: string,
  hashes: unknown,
  idToken: string,
  options?: StorageOptions & { albumsFileName?: string }
): Promise<AlbumRecord> => {
  const cleanName = name.trim()
  if (!cleanName) {
    throw createError({ statusCode: 400, statusMessage: 'Album name must be non-empty' })
  }
  const cleanHashes = normalizeHashes(hashes)
  const existing = await getAlbums(idToken, options)
  if (existing.some((album) => album.name.toLowerCase() === cleanName.toLowerCase())) {
    throw createError({ statusCode: 409, statusMessage: `Album '${cleanName}' already exists` })
  }

  const created: AlbumRecord = { name: cleanName, hashes: cleanHashes }
  await persistAlbums([...existing, created], idToken, options)
  return created
}

export const updateAlbum = async (
  name: string,
  hashes: unknown,
  idToken: string,
  options?: StorageOptions & { albumsFileName?: string }
): Promise<AlbumRecord> => {
  const cleanName = name.trim()
  const cleanHashes = normalizeHashes(hashes)
  const existing = await getAlbums(idToken, options)
  const index = existing.findIndex((album) => album.name === cleanName)
  if (index === -1) {
    throw createError({ statusCode: 404, statusMessage: `Album '${cleanName}' not found` })
  }

  const updated: AlbumRecord = { name: cleanName, hashes: cleanHashes }
  const next = existing.map((album, idx) => (idx === index ? updated : album))
  await persistAlbums(next, idToken, options)
  return updated
}

export const deleteAlbum = async (
  name: string,
  idToken: string,
  options?: StorageOptions & { albumsFileName?: string }
): Promise<void> => {
  const cleanName = name.trim()
  const existing = await getAlbums(idToken, options)
  const filtered = existing.filter((album) => album.name !== cleanName)
  if (filtered.length === existing.length) {
    throw createError({ statusCode: 404, statusMessage: `Album '${cleanName}' not found` })
  }
  await persistAlbums(filtered, idToken, options)
}

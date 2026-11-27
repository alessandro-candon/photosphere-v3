import { resolve } from 'node:path'
import { createError } from 'h3'
import { SHA1_REGEX, type AlbumSummary } from '#shared/index'
import type { AlbumRecord, MediaDatabaseSnapshot } from '../types/cache'
import { createAsyncMutex, createSingleFlight } from './async-mutex'
import {
  ensureMountedVolumeDirAsync,
  getDefaultCacheDir,
  loadJsonDatabaseWithMetadata,
  writeFileAtomicAsync,
  type StorageOptions,
} from './storage-download'
import { uploadDataFile } from './storage-upload'

export type AlbumSummaryDto = AlbumSummary

const CONTROL_CHAR_REGEX = /[\u0000-\u001f\u007f]/
const ALBUMS_FILENAME = 'photosphere_albums.json'

export interface AlbumMutationResult {
  album: AlbumSummaryDto | null
  generation: string | null
}

let albumsCache: AlbumRecord[] | null = null
let albumsGeneration: string | null = null
let albumsEpoch = 0
const withAlbumsWriteLock = createAsyncMutex()
const albumsSingleFlight = createSingleFlight<string, AlbumRecord[]>()

export const invalidateAlbumsCache = (): void => {
  albumsEpoch += 1
  albumsCache = null
  albumsGeneration = null
  albumsSingleFlight.clear()
}

export const getCachedAlbumsGeneration = (): string | null => albumsGeneration

export const setCachedAlbumsGenerationForTests = (gen: string | null): void => {
  albumsGeneration = gen
}

export const validateAlbumName = (raw: unknown): string => {
  if (typeof raw !== 'string') {
    throw createError({
      statusCode: 400,
      statusMessage: 'Album name must be a string',
    })
  }
  const trimmed = raw.trim()
  if (trimmed.length === 0 || trimmed.length > 120) {
    throw createError({
      statusCode: 400,
      statusMessage: 'Album name must be between 1 and 120 characters',
    })
  }
  if (trimmed.includes('/') || trimmed.includes('\\') || CONTROL_CHAR_REGEX.test(trimmed)) {
    throw createError({
      statusCode: 400,
      statusMessage: 'Album name cannot contain slashes or control characters',
    })
  }
  return trimmed
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
  const entryEpoch = albumsEpoch

  const loadAlbums = async (): Promise<AlbumRecord[]> => {
    try {
      const loaded = await loadJsonDatabaseWithMetadata(
        fileName,
        fileName,
        idToken,
        validateAlbumsPayload,
        options
      )
      if (entryEpoch === albumsEpoch) {
        albumsCache = loaded.data
        albumsGeneration = loaded.generation
      }
      return loaded.data
    } catch (error) {
      if ((error as { statusCode?: number }).statusCode === 404) {
        if (entryEpoch === albumsEpoch) {
          albumsCache = []
          albumsGeneration = '0'
        }
        return []
      }
      throw error
    }
  }

  if (options?.forceRefresh) {
    return await loadAlbums()
  }

  return await albumsSingleFlight.run(`${fileName}:${entryEpoch}`, loadAlbums)
}

export const toAlbumSummary = (
  album: AlbumRecord,
  snapshot?: MediaDatabaseSnapshot | null
): AlbumSummaryDto => {
  const coverThumbnails: string[] = []
  for (const hash of album.hashes) {
    if (coverThumbnails.length >= 4) break
    if (snapshot) {
      const rec = snapshot.recordsByHash[hash]
      if (!rec) continue
      if (rec.thumbnail_bucket_uri === null && rec.file_type !== 'IMAGE') continue
    }
    coverThumbnails.push(`/api/media/${hash}?variant=thumbnail`)
  }
  return {
    name: album.name,
    totalFiles: album.hashes.length,
    coverThumbnails,
  }
}

export const findAlbumIndexByName = (albums: AlbumRecord[], targetName: string): number => {
  const trimmed = targetName.trim()
  const exactIdx = albums.findIndex((a) => a.name === trimmed)
  if (exactIdx !== -1) return exactIdx
  const lower = trimmed.toLowerCase()
  return albums.findIndex((a) => a.name.trim().toLowerCase() === lower)
}

const persistAlbumsWriteThrough = async (
  nextAlbums: AlbumRecord[],
  idToken: string,
  options?: StorageOptions & { albumsFileName?: string }
): Promise<string | null> => {
  const fileName = options?.albumsFileName || ALBUMS_FILENAME
  const validated = validateAlbumsPayload(nextAlbums)
  const serialized = JSON.stringify(validated, null, 2)

  // Upload to GCS first with ifGenerationMatch; failure must leave local disk & memory untouched
  const uploadResult = await uploadDataFile(fileName, serialized, idToken, {
    ...options,
    ifGenerationMatch: albumsGeneration,
  })

  const mountedDir = await ensureMountedVolumeDirAsync(
    undefined,
    options?.mountedVolumePath ||
      process.env.PHOTOSPHERE_MOUNTED_VOLUME_PATH ||
      getDefaultCacheDir()
  )
  const localPath = resolve(mountedDir, fileName)
  const metaPath = `${localPath}.meta.json`
  await writeFileAtomicAsync(localPath, serialized)
  await writeFileAtomicAsync(metaPath, JSON.stringify({ generation: uploadResult.generation }))

  albumsEpoch += 1
  albumsSingleFlight.clear()
  albumsCache = validated
  albumsGeneration = uploadResult.generation

  return albumsGeneration
}

export const createAlbum = async (
  input: { name: unknown; hashes?: unknown },
  idToken: string,
  options?: StorageOptions & { albumsFileName?: string },
  snapshot?: MediaDatabaseSnapshot | null
): Promise<AlbumMutationResult> => {
  const cleanName = validateAlbumName(input.name)
  const cleanHashes = input.hashes !== undefined ? normalizeHashes(input.hashes) : []

  return await withAlbumsWriteLock(async () => {
    const current = await getAlbums(idToken, options)
    if (findAlbumIndexByName(current, cleanName) !== -1) {
      throw createError({
        statusCode: 409,
        statusMessage: `Album '${cleanName}' already exists`,
      })
    }

    const created: AlbumRecord = { name: cleanName, hashes: cleanHashes }
    const nextAlbums = [...current, created]
    const generation = await persistAlbumsWriteThrough(nextAlbums, idToken, options)
    return {
      album: toAlbumSummary(created, snapshot),
      generation,
    }
  })
}

export const updateAlbum = async (
  targetName: string,
  patch: { newName?: unknown; addHashes?: unknown; removeHashes?: unknown },
  idToken: string,
  options?: StorageOptions & { albumsFileName?: string },
  snapshot?: MediaDatabaseSnapshot | null
): Promise<AlbumMutationResult> => {
  return await withAlbumsWriteLock(async () => {
    const current = await getAlbums(idToken, options)
    const idx = findAlbumIndexByName(current, targetName)
    if (idx === -1) {
      throw createError({
        statusCode: 404,
        statusMessage: `Album not found: ${targetName}`,
      })
    }

    const existing = current[idx]!
    let nextName = existing.name
    if (patch.newName !== undefined) {
      const candidate = validateAlbumName(patch.newName)
      const collisionIdx = findAlbumIndexByName(current, candidate)
      if (collisionIdx !== -1 && collisionIdx !== idx) {
        throw createError({
          statusCode: 409,
          statusMessage: `Album '${candidate}' already exists`,
        })
      }
      nextName = candidate
    }

    let nextHashes = [...existing.hashes]
    if (patch.addHashes !== undefined) {
      const toAdd = normalizeHashes(patch.addHashes)
      const existingSet = new Set(nextHashes)
      for (const h of toAdd) {
        if (!existingSet.has(h)) {
          existingSet.add(h)
          nextHashes.push(h)
        }
      }
    }
    if (patch.removeHashes !== undefined) {
      const toRemove = new Set(normalizeHashes(patch.removeHashes))
      nextHashes = nextHashes.filter((h) => !toRemove.has(h))
    }

    const updated: AlbumRecord = { name: nextName, hashes: nextHashes }
    const nextAlbums = current.map((entry, i) => (i === idx ? updated : entry))
    const generation = await persistAlbumsWriteThrough(nextAlbums, idToken, options)
    return {
      album: toAlbumSummary(updated, snapshot),
      generation,
    }
  })
}

export const deleteAlbum = async (
  targetName: string,
  idToken: string,
  options?: StorageOptions & { albumsFileName?: string }
): Promise<{ generation: string | null; deletedName: string }> => {
  return await withAlbumsWriteLock(async () => {
    const current = await getAlbums(idToken, options)
    const idx = findAlbumIndexByName(current, targetName)
    if (idx === -1) {
      throw createError({
        statusCode: 404,
        statusMessage: `Album not found: ${targetName}`,
      })
    }

    const deletedName = current[idx]!.name
    const nextAlbums = current.filter((_, i) => i !== idx)
    const generation = await persistAlbumsWriteThrough(nextAlbums, idToken, options)
    return { generation, deletedName }
  })
}

import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { randomUUID } from 'node:crypto'
import { createError } from 'h3'
import { parseGsUri } from './url'
import { logger } from '../services/logger.service'

export interface StorageOptions {
  dataBucket?: string
  mediaBucket?: string
  mountedVolumePath?: string
  fetchImpl?: typeof fetch
  forceRefresh?: boolean
}

const getStorageConfig = (options?: StorageOptions) => {
  return {
    dataBucket: options?.dataBucket ?? process.env.PHOTOSPHERE_DATA_BUCKET ?? '',
    mediaBucket: options?.mediaBucket ?? process.env.PHOTOSPHERE_MEDIA_BUCKET ?? '',
    mountedVolumePath:
      options?.mountedVolumePath ??
      process.env.PHOTOSPHERE_MOUNTED_VOLUME_PATH ??
      '/mnt/photosphere',
    fetchImpl: options?.fetchImpl ?? globalThis.fetch,
  }
}

export const buildFirebaseMediaReadUrl = (bucket: string, objectName: string): string => {
  const emulatorHost =
    process.env.STORAGE_EMULATOR_HOST || process.env.FIREBASE_STORAGE_EMULATOR_HOST
  if (emulatorHost) {
    const cleanHost = emulatorHost.replace(/\/+$/, '')
    return `${cleanHost}/storage/v1/b/${encodeURIComponent(bucket)}/o/${encodeURIComponent(objectName)}?alt=media`
  }
  return `https://firebasestorage.googleapis.com/v0/b/${encodeURIComponent(bucket)}/o/${encodeURIComponent(objectName)}?alt=media`
}

export const buildFirebaseMediaUploadUrl = (bucket: string, objectName: string): string => {
  const emulatorHost =
    process.env.STORAGE_EMULATOR_HOST || process.env.FIREBASE_STORAGE_EMULATOR_HOST
  if (emulatorHost) {
    const cleanHost = emulatorHost.replace(/\/+$/, '')
    return `${cleanHost}/upload/storage/v1/b/${encodeURIComponent(bucket)}/o?uploadType=media&name=${encodeURIComponent(objectName)}`
  }
  return `https://firebasestorage.googleapis.com/v0/b/${encodeURIComponent(bucket)}/o?uploadType=media&name=${encodeURIComponent(objectName)}`
}

export const ensureMountedVolumeDir = (subDir?: string, volumePathOverride?: string): string => {
  const base =
    volumePathOverride || process.env.PHOTOSPHERE_MOUNTED_VOLUME_PATH || '/mnt/photosphere'
  const target = subDir ? resolve(base, subDir) : resolve(base)
  mkdirSync(target, { recursive: true })
  return target
}

export const writeFileAtomic = (targetPath: string, data: string | Uint8Array): void => {
  mkdirSync(dirname(targetPath), { recursive: true })
  const tmpPath = `${targetPath}.${randomUUID()}.tmp`
  writeFileSync(tmpPath, data)
  renameSync(tmpPath, targetPath)
}

export const downloadDataFile = async (
  fileName: string,
  idToken: string,
  options?: StorageOptions
): Promise<string> => {
  const cfg = getStorageConfig(options)
  if (!cfg.dataBucket) {
    throw createError({
      statusCode: 500,
      statusMessage: 'Server misconfiguration: PHOTOSPHERE_DATA_BUCKET is not configured',
    })
  }

  const url = buildFirebaseMediaReadUrl(cfg.dataBucket, fileName)
  const response = await cfg.fetchImpl(url, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${idToken}`,
    },
  })

  if (!response.ok) {
    throw createError({
      statusCode:
        response.status === 404
          ? 404
          : response.status === 401 || response.status === 403
            ? response.status
            : 502,
      statusMessage: `Failed to download data object ${fileName} from ${cfg.dataBucket} (${response.status})`,
    })
  }

  return await response.text()
}

export const uploadDataFile = async (
  fileName: string,
  jsonBytes: string | Uint8Array,
  idToken: string,
  options?: StorageOptions
): Promise<void> => {
  const cfg = getStorageConfig(options)
  if (!cfg.dataBucket) {
    throw createError({
      statusCode: 500,
      statusMessage: 'Server misconfiguration: PHOTOSPHERE_DATA_BUCKET is not configured',
    })
  }

  const url = buildFirebaseMediaUploadUrl(cfg.dataBucket, fileName)
  const bodyContent = typeof jsonBytes === 'string' ? jsonBytes : Buffer.from(jsonBytes)
  const response = await cfg.fetchImpl(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${idToken}`,
      'Content-Type': 'application/json',
    },
    body: bodyContent,
  })

  if (!response.ok) {
    throw createError({
      statusCode: response.status === 401 || response.status === 403 ? response.status : 502,
      statusMessage: `Failed to upload data object ${fileName} to ${cfg.dataBucket} (${response.status})`,
    })
  }

  logger.info({ bucketTier: 'data', bucket: cfg.dataBucket, fileName }, 'uploaded_data_object')
}

export const fetchMediaObject = async (
  bucketUri: string,
  idToken: string,
  options?: StorageOptions & { rangeHeader?: string }
): Promise<Response> => {
  const cfg = getStorageConfig(options)
  const parsed = parseGsUri(bucketUri)
  if (!parsed) {
    throw createError({ statusCode: 400, statusMessage: 'Invalid gs:// media URI' })
  }
  if (!cfg.mediaBucket) {
    throw createError({
      statusCode: 500,
      statusMessage: 'Server misconfiguration: PHOTOSPHERE_MEDIA_BUCKET is not configured',
    })
  }
  if (parsed.bucket !== cfg.mediaBucket) {
    throw createError({
      statusCode: 403,
      statusMessage: `Forbidden: Bucket ${parsed.bucket} is not the configured media bucket`,
    })
  }

  const url = buildFirebaseMediaReadUrl(cfg.mediaBucket, parsed.objectPath)
  const headers: Record<string, string> = {
    Authorization: `Bearer ${idToken}`,
  }
  if (options?.rangeHeader) {
    headers.Range = options.rangeHeader
  }

  const response = await cfg.fetchImpl(url, {
    method: 'GET',
    headers,
  })

  if (!response.ok && response.status !== 206) {
    throw createError({
      statusCode:
        response.status === 404
          ? 404
          : response.status === 401 || response.status === 403
            ? response.status
            : 502,
      statusMessage: `Failed to stream media object ${parsed.objectPath} (${response.status})`,
    })
  }

  return response
}

export const loadJsonDatabase = async <T>(
  localFileName: string,
  remoteFileName: string,
  idToken: string,
  validator: (parsed: unknown) => T,
  options?: StorageOptions
): Promise<T> => {
  const cfg = getStorageConfig(options)
  const dir = ensureMountedVolumeDir(undefined, cfg.mountedVolumePath)
  const localPath = resolve(dir, localFileName)

  if (!options?.forceRefresh && existsSync(localPath)) {
    const rawDisk = readFileSync(localPath, 'utf-8')
    let parsedDisk: unknown
    try {
      parsedDisk = JSON.parse(rawDisk)
    } catch {
      throw createError({
        statusCode: 500,
        statusMessage: `Corrupted JSON in cached database file ${localFileName}`,
      })
    }
    return validator(parsedDisk)
  }

  const rawRemote = await downloadDataFile(remoteFileName, idToken, options)
  let parsedRemote: unknown
  try {
    parsedRemote = JSON.parse(rawRemote)
  } catch {
    throw createError({
      statusCode: 500,
      statusMessage: `Invalid JSON downloaded for ${remoteFileName}`,
    })
  }

  const validated = validator(parsedRemote)
  writeFileAtomic(localPath, JSON.stringify(parsedRemote))
  return validated
}

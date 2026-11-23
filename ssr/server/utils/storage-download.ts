import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { randomUUID } from 'node:crypto'
import { createError } from 'h3'

export interface StorageOptions {
  dataBucket?: string
  mediaBucket?: string
  mountedVolumePath?: string
  fetchImpl?: typeof fetch
  forceRefresh?: boolean
}

export interface DownloadedJsonResult<T> {
  data: T
  generation: string | null
}

export interface DownloadedMediaResult {
  status: number
  contentType: string
  contentLength: number | null
  contentRange: string | null
  body: Uint8Array
}

export const getDefaultCacheDir = (): string => resolve(process.cwd(), '.photosphere-cache')

const getStorageConfig = (options?: StorageOptions) => {
  return {
    dataBucket: options?.dataBucket ?? process.env.PHOTOSPHERE_DATA_BUCKET ?? '',
    mountedVolumePath:
      options?.mountedVolumePath ??
      process.env.PHOTOSPHERE_MOUNTED_VOLUME_PATH ??
      getDefaultCacheDir(),
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

export const parseGsUri = (gsUri: string): { bucket: string; objectPath: string } => {
  if (!gsUri || !gsUri.startsWith('gs://')) {
    throw createError({
      statusCode: 500,
      statusMessage: `Invalid GCS URI: ${String(gsUri)}`,
    })
  }
  const withoutScheme = gsUri.slice(5)
  const slashIndex = withoutScheme.indexOf('/')
  if (slashIndex <= 0 || slashIndex === withoutScheme.length - 1) {
    throw createError({
      statusCode: 500,
      statusMessage: `Malformed GCS URI missing bucket or object path: ${gsUri}`,
    })
  }
  return {
    bucket: withoutScheme.slice(0, slashIndex),
    objectPath: withoutScheme.slice(slashIndex + 1),
  }
}

export const ensureMountedVolumeDir = (subDir?: string, volumePathOverride?: string): string => {
  const base =
    volumePathOverride || process.env.PHOTOSPHERE_MOUNTED_VOLUME_PATH || getDefaultCacheDir()
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

export const downloadDataFileWithMetadata = async (
  fileName: string,
  idToken: string,
  options?: StorageOptions
): Promise<{ text: string; generation: string | null }> => {
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

  return {
    text: await response.text(),
    generation: response.headers.get('x-goog-generation'),
  }
}

export const downloadDataFile = async (
  fileName: string,
  idToken: string,
  options?: StorageOptions
): Promise<string> => {
  const result = await downloadDataFileWithMetadata(fileName, idToken, options)
  return result.text
}

export const downloadMediaObject = async (
  gsUri: string,
  idToken: string,
  options?: StorageOptions & { rangeHeader?: string }
): Promise<DownloadedMediaResult> => {
  const cfg = getStorageConfig(options)
  const { bucket, objectPath } = parseGsUri(gsUri)
  const url = buildFirebaseMediaReadUrl(bucket, objectPath)

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

  if (!response.ok) {
    throw createError({
      statusCode:
        response.status === 404
          ? 404
          : response.status === 416
            ? 416
            : response.status === 401 || response.status === 403
              ? response.status
              : 502,
      statusMessage: `Failed to download media object ${objectPath} from ${bucket} (${response.status})`,
    })
  }

  const arrayBuffer = await response.arrayBuffer()
  const rawLength = response.headers.get('content-length')
  const parsedLength = rawLength ? Number(rawLength) : null

  return {
    status: response.status,
    contentType: response.headers.get('content-type') || 'application/octet-stream',
    contentLength: parsedLength !== null && Number.isFinite(parsedLength) ? parsedLength : null,
    contentRange: response.headers.get('content-range'),
    body: new Uint8Array(arrayBuffer),
  }
}

export const loadJsonDatabaseWithMetadata = async <T>(
  localFileName: string,
  remoteFileName: string,
  idToken: string,
  validator: (parsed: unknown) => T,
  options?: StorageOptions
): Promise<DownloadedJsonResult<T>> => {
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
    return {
      data: validator(parsedDisk),
      generation: null,
    }
  }

  const remote = await downloadDataFileWithMetadata(remoteFileName, idToken, options)
  let parsedRemote: unknown
  try {
    parsedRemote = JSON.parse(remote.text)
  } catch {
    throw createError({
      statusCode: 500,
      statusMessage: `Invalid JSON downloaded for ${remoteFileName}`,
    })
  }

  const validated = validator(parsedRemote)
  writeFileAtomic(localPath, JSON.stringify(parsedRemote))
  return {
    data: validated,
    generation: remote.generation,
  }
}

export const loadJsonDatabase = async <T>(
  localFileName: string,
  remoteFileName: string,
  idToken: string,
  validator: (parsed: unknown) => T,
  options?: StorageOptions
): Promise<T> => {
  const result = await loadJsonDatabaseWithMetadata(
    localFileName,
    remoteFileName,
    idToken,
    validator,
    options
  )
  return result.data
}

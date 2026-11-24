import { createError } from 'h3'
import type { StorageOptions } from './storage-download'

export interface UploadDataFileOptions extends StorageOptions {
  ifGenerationMatch?: string | null
  contentType?: string
}

export interface UploadDataFileResult {
  generation: string | null
}

export const buildFirebaseMediaUploadUrl = (
  bucket: string,
  objectName: string,
  ifGenerationMatch?: string | null
): string => {
  const emulatorHost =
    process.env.STORAGE_EMULATOR_HOST || process.env.FIREBASE_STORAGE_EMULATOR_HOST

  if (emulatorHost) {
    const cleanHost = emulatorHost.replace(/\/+$/, '')
    const genQuery = ifGenerationMatch
      ? `&ifGenerationMatch=${encodeURIComponent(ifGenerationMatch)}`
      : ''
    return `${cleanHost}/upload/storage/v1/b/${encodeURIComponent(bucket)}/o?uploadType=media&name=${encodeURIComponent(objectName)}${genQuery}`
  }

  return `https://firebasestorage.googleapis.com/v0/b/${encodeURIComponent(bucket)}/o?uploadType=media&name=${encodeURIComponent(objectName)}`
}

export const uploadDataFile = async (
  fileName: string,
  content: string,
  idToken: string,
  options?: UploadDataFileOptions
): Promise<UploadDataFileResult> => {
  const dataBucket = options?.dataBucket ?? process.env.PHOTOSPHERE_DATA_BUCKET ?? ''
  if (!dataBucket) {
    throw createError({
      statusCode: 500,
      statusMessage: 'Server misconfiguration: PHOTOSPHERE_DATA_BUCKET is not configured',
    })
  }

  const fetchImpl = options?.fetchImpl ?? globalThis.fetch
  const url = buildFirebaseMediaUploadUrl(dataBucket, fileName, options?.ifGenerationMatch)

  const headers: Record<string, string> = {
    Authorization: `Bearer ${idToken}`,
    'Content-Type': options?.contentType || 'application/json',
  }
  if (options?.ifGenerationMatch) {
    headers['x-goog-if-generation-match'] = options.ifGenerationMatch
  }

  const response = await fetchImpl(url, {
    method: 'POST',
    headers,
    body: content,
  })

  if (response.status === 412) {
    throw createError({
      statusCode: 409,
      statusMessage: 'Conflict: Albums were modified concurrently; please reload and retry',
    })
  }

  if (!response.ok) {
    throw createError({
      statusCode: response.status === 401 || response.status === 403 ? response.status : 502,
      statusMessage: `Failed to upload ${fileName} to ${dataBucket} (${response.status})`,
    })
  }

  let generation = response.headers.get('x-goog-generation')
  try {
    const text = await response.text()
    if (text) {
      const parsed = JSON.parse(text) as { generation?: string | number }
      if (parsed && parsed.generation !== undefined && parsed.generation !== null) {
        generation = String(parsed.generation)
      }
    }
  } catch {
    // Ignore non-JSON upload bodies if generation header was provided
  }

  return { generation }
}

import { createError, getHeader, type H3Event } from 'h3'
import { useRuntimeConfig } from '#imports'
import { extractBearerToken } from '../services/auth.service'
import { getDefaultCacheDir, type StorageOptions } from './storage-download'

export const requireBearerToken = (event: H3Event): string => {
  const token = extractBearerToken(getHeader(event, 'authorization')) || event.context.idToken
  if (!token) {
    throw createError({ statusCode: 401, statusMessage: 'Unauthorized: Missing Bearer token' })
  }
  return token
}

export const getRuntimeStorageOptions = (event: H3Event): StorageOptions => {
  const cfg = useRuntimeConfig(event)
  return {
    dataBucket: cfg.storage?.dataBucket || '',
    mediaBucket: cfg.storage?.mediaBucket || '',
    mountedVolumePath: cfg.storage?.mountedVolumePath || getDefaultCacheDir(),
  }
}

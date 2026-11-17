import {
  createError,
  defineEventHandler,
  getHeader,
  getRouterParam,
  sendStream,
  setHeader,
  setResponseStatus,
} from 'h3'
import { serveCachedMediaObject } from '../../services/media-cache.service'
import { getRuntimeMediaCacheConfigs, requireBearerToken } from '../../utils/runtime-storage'

export default defineEventHandler(async (event) => {
  const idToken = requireBearerToken(event)
  const rawPath = getRouterParam(event, 'path') || ''
  if (!rawPath) {
    throw createError({ statusCode: 400, statusMessage: 'Missing media object path' })
  }

  let decodedPath: string
  try {
    decodedPath = rawPath
      .split('/')
      .map((segment) => decodeURIComponent(segment))
      .join('/')
  } catch {
    throw createError({ statusCode: 400, statusMessage: 'Malformed URL encoding in media path' })
  }

  const configs = getRuntimeMediaCacheConfigs(event)
  const rangeHeader = getHeader(event, 'range')

  const result = await serveCachedMediaObject(decodedPath, idToken, configs, {
    rangeHeader,
  })

  setResponseStatus(event, result.statusCode)
  setHeader(event, 'Content-Type', result.contentType)
  setHeader(event, 'Accept-Ranges', result.acceptRanges)
  setHeader(event, 'Cache-Control', 'private, max-age=3600')
  if (result.contentLength !== null) {
    setHeader(event, 'Content-Length', result.contentLength)
  }
  if (result.contentRange) {
    setHeader(event, 'Content-Range', result.contentRange)
  }

  return sendStream(event, result.stream)
})

import { defineEventHandler, getHeader, type H3Event } from 'h3'
import { useRuntimeConfig } from '#imports'
import {
  MEDIA_COOKIE_NAME,
  extractBearerToken,
  extractCookieValue,
  verifyAuthorizedUser,
  verifyMediaSessionCookieValue,
  type VerifyTokenFn,
} from '../services/auth.service'
import { getEventLogger } from '../services/logger.service'

export const authenticateApiRequest = async (
  event: H3Event,
  verifyToken?: VerifyTokenFn,
  allowedEmailsOverride?: string[] | string,
  sessionSecretOverride?: string
): Promise<void> => {
  const rawPath = event.path || ''
  const pathname = rawPath.split('?')[0] || ''
  const method = (event.method || event.node?.req?.method || 'GET').toUpperCase()

  if (
    !pathname.startsWith('/api/') ||
    pathname === '/api/healthz' ||
    pathname === '/api/readyz' ||
    (pathname === '/api/auth/session' && method === 'DELETE')
  ) {
    return
  }

  const runtimeConfig = useRuntimeConfig(event)
  const allowedEmails = allowedEmailsOverride ?? runtimeConfig.auth?.allowedEmails
  const sessionSecret = sessionSecretOverride ?? runtimeConfig.auth?.sessionSecret
  const authHeader = getHeader(event, 'authorization')

  try {
    if (pathname.startsWith('/api/media/') && method === 'GET') {
      if (authHeader) {
        const authUser = await verifyAuthorizedUser(authHeader, allowedEmails, verifyToken)
        event.context.auth = authUser
        event.context.idToken = extractBearerToken(authHeader) || undefined
        return
      }
      const cookieHeader = getHeader(event, 'cookie')
      const cookieVal = extractCookieValue(cookieHeader, MEDIA_COOKIE_NAME)
      const verified = verifyMediaSessionCookieValue(cookieVal, allowedEmails, sessionSecret)
      event.context.auth = verified.user
      event.context.idToken = verified.idToken
      return
    }

    const authUser = await verifyAuthorizedUser(authHeader, allowedEmails, verifyToken)
    event.context.auth = authUser
    event.context.idToken = extractBearerToken(authHeader) || undefined
  } catch (error) {
    getEventLogger(event).warn(
      {
        path: pathname,
        method,
        statusCode: (error as { statusCode?: number }).statusCode || 401,
      },
      'api_auth_denied'
    )
    throw error
  }
}

export default defineEventHandler(async (event) => {
  await authenticateApiRequest(event)
})

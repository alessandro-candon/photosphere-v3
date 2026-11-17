import { defineEventHandler, getHeader, type H3Event } from 'h3'
import { useRuntimeConfig } from '#imports'
import { verifyAuthorizedUser, type VerifyTokenFn } from '../services/auth.service'
import { getEventLogger } from '../services/logger.service'

export const authenticateApiRequest = async (
  event: H3Event,
  verifyToken?: VerifyTokenFn,
  allowedEmailsOverride?: string[] | string
): Promise<void> => {
  const rawPath = event.path || ''
  const pathname = rawPath.split('?')[0] || ''

  if (!pathname.startsWith('/api/') || pathname === '/api/healthz') {
    return
  }

  const runtimeConfig = useRuntimeConfig(event)
  const allowedEmails = allowedEmailsOverride ?? runtimeConfig.auth?.allowedEmails
  const authHeader = getHeader(event, 'authorization')

  try {
    const authUser = await verifyAuthorizedUser(authHeader, allowedEmails, verifyToken)
    event.context.auth = authUser
  } catch (error) {
    getEventLogger(event).warn(
      {
        path: pathname,
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

import { createError, defineEventHandler, setCookie } from 'h3'
import { useRuntimeConfig } from '#imports'
import {
  MEDIA_COOKIE_NAME,
  createMediaSessionCookieValue,
  resolveMediaSessionMaxAge,
} from '../../services/auth.service'
import { requireBearerToken } from '../../utils/runtime-storage'

export default defineEventHandler((event) => {
  const auth = event.context.auth
  if (!auth?.email) {
    throw createError({
      statusCode: 401,
      statusMessage: 'Unauthorized: Verified session required',
    })
  }

  const idToken = requireBearerToken(event)
  const cfg = useRuntimeConfig(event)
  const maxAge = resolveMediaSessionMaxAge(idToken, 3600)
  const mountedVolumePath = cfg.storage?.mountedVolumePath
  const cookieValue = createMediaSessionCookieValue(
    auth,
    idToken,
    cfg.auth?.sessionSecret,
    maxAge,
    mountedVolumePath
  )

  setCookie(event, MEDIA_COOKIE_NAME, cookieValue, {
    httpOnly: true,
    sameSite: 'lax',
    path: '/api/media',
    maxAge,
    secure: process.env.NODE_ENV === 'production',
  })

  return {
    authenticated: true,
    email: auth.email,
  }
})

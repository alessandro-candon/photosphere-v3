import { createHmac, randomBytes, timingSafeEqual } from 'node:crypto'
import { createError } from 'h3'
import { getAuth, type DecodedIdToken } from 'firebase-admin/auth'
import { ensureFirebaseAdminInitialized } from './firebase-admin.service'
import type { AuthUser } from '../types/auth'

export type VerifyTokenFn = (idToken: string) => Promise<DecodedIdToken>

export const MEDIA_COOKIE_NAME = '__ps_media'

const FALLBACK_SESSION_SECRET = randomBytes(32).toString('hex')

interface MediaSessionPayload {
  uid: string
  email: string
  email_verified: true
  idToken: string
  exp: number
  name?: string
  picture?: string
}

const resolveSessionSecret = (secret?: string): string => {
  const candidate = (secret || process.env.PHOTOSPHERE_SESSION_SECRET || '').trim()
  return candidate || FALLBACK_SESSION_SECRET
}

export const normalizeAllowedEmails = (allowed: string[] | string | undefined): string[] => {
  if (!allowed) {
    return []
  }
  const items = Array.isArray(allowed) ? allowed : allowed.split(',')
  return items.map((email) => email.trim().toLowerCase()).filter(Boolean)
}

export const extractBearerToken = (authHeader: string | undefined): string | null => {
  if (!authHeader || typeof authHeader !== 'string') {
    return null
  }
  const match = authHeader.match(/^Bearer\s+(\S+)$/i)
  return match?.[1] || null
}

export const extractCookieValue = (
  cookieHeader: string | undefined,
  name: string
): string | null => {
  if (!cookieHeader || typeof cookieHeader !== 'string') {
    return null
  }
  const pairs = cookieHeader.split(';')
  for (const pair of pairs) {
    const eqIndex = pair.indexOf('=')
    if (eqIndex <= 0) continue
    const key = pair.slice(0, eqIndex).trim()
    if (key === name) {
      const val = pair.slice(eqIndex + 1).trim()
      try {
        return decodeURIComponent(val)
      } catch {
        return val
      }
    }
  }
  return null
}

const defaultVerifyToken: VerifyTokenFn = async (idToken: string) => {
  ensureFirebaseAdminInitialized()
  return await getAuth().verifyIdToken(idToken, true)
}

export const verifyAuthorizedUser = async (
  authHeader: string | undefined,
  allowedEmails: string[] | string | undefined,
  verifyToken: VerifyTokenFn = defaultVerifyToken
): Promise<AuthUser> => {
  const token = extractBearerToken(authHeader)
  if (!token) {
    throw createError({
      statusCode: 401,
      statusMessage: 'Unauthorized: Missing or malformed Bearer token',
    })
  }

  let decoded: DecodedIdToken
  try {
    decoded = await verifyToken(token)
  } catch {
    throw createError({
      statusCode: 401,
      statusMessage: 'Unauthorized: Invalid or expired Firebase ID token',
    })
  }

  if (decoded.email_verified !== true) {
    throw createError({
      statusCode: 403,
      statusMessage: 'Forbidden: Email address must be verified',
    })
  }

  const email = typeof decoded.email === 'string' ? decoded.email.trim().toLowerCase() : ''
  const allowlist = normalizeAllowedEmails(allowedEmails)

  if (!email || allowlist.length === 0 || !allowlist.includes(email)) {
    throw createError({
      statusCode: 403,
      statusMessage: 'Forbidden: Account is not in ALLOWED_EMAILS',
    })
  }

  return {
    uid: decoded.uid,
    email,
    email_verified: true,
    ...(typeof decoded.name === 'string' ? { name: decoded.name } : {}),
    ...(typeof decoded.picture === 'string' ? { picture: decoded.picture } : {}),
  }
}

export const createMediaSessionCookieValue = (
  user: AuthUser,
  idToken: string,
  secret?: string,
  maxAgeSeconds = 3600
): string => {
  const email = (user.email || '').trim().toLowerCase()
  if (!email || !user.uid || !idToken) {
    throw createError({
      statusCode: 401,
      statusMessage: 'Unauthorized: Cannot mint media session without verified identity',
    })
  }
  const payload: MediaSessionPayload = {
    uid: user.uid,
    email,
    email_verified: true,
    idToken,
    exp: Math.floor(Date.now() / 1000) + maxAgeSeconds,
    ...(user.name ? { name: user.name } : {}),
    ...(user.picture ? { picture: user.picture } : {}),
  }
  const encoded = Buffer.from(JSON.stringify(payload), 'utf-8').toString('base64url')
  const sig = createHmac('sha256', resolveSessionSecret(secret)).update(encoded).digest('base64url')
  return `${encoded}.${sig}`
}

export const verifyMediaSessionCookieValue = (
  cookieValue: string | undefined | null,
  allowedEmails: string[] | string | undefined,
  secret?: string
): { user: AuthUser; idToken: string } => {
  if (!cookieValue || typeof cookieValue !== 'string') {
    throw createError({
      statusCode: 401,
      statusMessage: 'Unauthorized: Missing media session cookie',
    })
  }

  const dotIdx = cookieValue.indexOf('.')
  if (dotIdx <= 0 || dotIdx === cookieValue.length - 1) {
    throw createError({
      statusCode: 401,
      statusMessage: 'Unauthorized: Malformed media session cookie',
    })
  }

  const encoded = cookieValue.slice(0, dotIdx)
  const sigB64 = cookieValue.slice(dotIdx + 1)
  const expectedDigest = createHmac('sha256', resolveSessionSecret(secret)).update(encoded).digest()
  const actualDigest = Buffer.from(sigB64, 'base64url')

  if (
    expectedDigest.length !== actualDigest.length ||
    !timingSafeEqual(expectedDigest, actualDigest)
  ) {
    throw createError({
      statusCode: 401,
      statusMessage: 'Unauthorized: Invalid media session signature',
    })
  }

  let payload: MediaSessionPayload
  try {
    payload = JSON.parse(Buffer.from(encoded, 'base64url').toString('utf-8')) as MediaSessionPayload
  } catch {
    throw createError({
      statusCode: 401,
      statusMessage: 'Unauthorized: Invalid media session payload',
    })
  }

  if (!payload || typeof payload.exp !== 'number' || payload.exp <= Math.floor(Date.now() / 1000)) {
    throw createError({
      statusCode: 401,
      statusMessage: 'Unauthorized: Media session cookie expired',
    })
  }

  if (payload.email_verified !== true) {
    throw createError({
      statusCode: 403,
      statusMessage: 'Forbidden: Email address must be verified',
    })
  }

  const email = typeof payload.email === 'string' ? payload.email.trim().toLowerCase() : ''
  const allowlist = normalizeAllowedEmails(allowedEmails)
  if (!email || allowlist.length === 0 || !allowlist.includes(email)) {
    throw createError({
      statusCode: 403,
      statusMessage: 'Forbidden: Account is not in ALLOWED_EMAILS',
    })
  }

  if (!payload.idToken) {
    throw createError({
      statusCode: 401,
      statusMessage: 'Unauthorized: Missing upstream token in media session',
    })
  }

  return {
    user: {
      uid: payload.uid,
      email,
      email_verified: true,
      ...(payload.name ? { name: payload.name } : {}),
      ...(payload.picture ? { picture: payload.picture } : {}),
    },
    idToken: payload.idToken,
  }
}

export const assertAdminUser = (
  authUser: AuthUser | undefined,
  adminEmail: string | undefined
): void => {
  const expected = (adminEmail || '').trim().toLowerCase()
  const actual = (authUser?.email || '').trim().toLowerCase()
  if (!expected || !actual || actual !== expected) {
    throw createError({
      statusCode: 403,
      statusMessage: 'Forbidden: Admin access required',
    })
  }
}

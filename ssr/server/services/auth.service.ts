import { createError } from 'h3'
import { getAuth, type DecodedIdToken } from 'firebase-admin/auth'
import { ensureFirebaseAdminInitialized } from './firebase-admin.service'
import type { AuthUser } from '../types/auth'

export type VerifyTokenFn = (idToken: string) => Promise<DecodedIdToken>

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

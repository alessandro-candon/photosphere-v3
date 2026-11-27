import { IncomingMessage, ServerResponse } from 'node:http'
import { mkdtempSync, readFileSync, rmSync, statSync } from 'node:fs'
import { Socket } from 'node:net'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { createEvent, type H3Event } from 'h3'
import type { DecodedIdToken } from 'firebase-admin/auth'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import meHandler from '../../server/api/me.get'
import sessionDeleteHandler from '../../server/api/auth/session.delete'
import sessionPostHandler from '../../server/api/auth/session.post'
import { attachRequestLogger } from '../../server/middleware/00.request-logger'
import { authenticateApiRequest } from '../../server/middleware/auth'
import {
  MEDIA_COOKIE_NAME,
  assertAdminUser,
  createMediaSessionCookieValue,
  extractBearerToken,
  normalizeAllowedEmails,
  resolveMediaSessionMaxAge,
  resolveSessionSecret,
  verifyAuthorizedUser,
  verifyMediaSessionCookieValue,
} from '../../server/services/auth.service'
import { setMockRuntimeConfig } from '../nuxt-imports-stub'

const makeEvent = (
  path: string,
  options: { method?: string; authorization?: string; cookie?: string } = {}
): H3Event => {
  const req = new IncomingMessage(new Socket())
  req.url = path
  req.method = options.method || 'GET'
  if (options.authorization) {
    req.headers.authorization = options.authorization
  }
  if (options.cookie) {
    req.headers.cookie = options.cookie
  }
  const res = new ServerResponse(req)
  return createEvent(req, res)
}

const makeDecodedToken = (overrides: Partial<DecodedIdToken> = {}): DecodedIdToken =>
  ({
    uid: 'user-123',
    email: 'User@Example.com',
    email_verified: true,
    aud: 'proj',
    auth_time: 1000,
    exp: 9999999999,
    firebase: { identities: {}, sign_in_provider: 'google.com' },
    iat: 1000,
    iss: 'https://securetoken.google.com/proj',
    sub: 'user-123',
    ...overrides,
  }) as DecodedIdToken

describe('Server Auth Middleware, Media Session Cookie & Email Allowlist', () => {
  const tempDirs: string[] = []

  afterEach(() => {
    for (const dir of tempDirs.splice(0)) {
      rmSync(dir, { recursive: true, force: true })
    }
  })

  beforeEach(() => {
    setMockRuntimeConfig({
      auth: {
        allowedEmails: ['user@example.com', 'admin@example.com'],
        adminEmail: 'admin@example.com',
        sessionSecret: 'test-session-secret',
      },
    })
  })

  it('extracts bearer tokens and normalizes allowlists cleanly', () => {
    expect(extractBearerToken('Bearer abc.def')).toBe('abc.def')
    expect(extractBearerToken('bearer token123')).toBe('token123')
    expect(extractBearerToken('Basic foo')).toBeNull()
    expect(extractBearerToken(undefined)).toBeNull()
    expect(normalizeAllowedEmails(' A@B.com , c@d.com ')).toEqual(['a@b.com', 'c@d.com'])
  })

  it('allows /api/healthz and /api/readyz publicly without Bearer token', async () => {
    const verifyFn = vi.fn()
    await authenticateApiRequest(makeEvent('/api/healthz'), verifyFn)
    await authenticateApiRequest(makeEvent('/api/readyz'), verifyFn)
    await authenticateApiRequest(makeEvent('/api/auth/session', { method: 'DELETE' }), verifyFn)
    expect(verifyFn).not.toHaveBeenCalled()
  })

  it('attaches requestId via 00.request-logger before auth denials occur', async () => {
    const event = makeEvent('/api/files')
    attachRequestLogger(event)
    expect(event.context.requestId).toBeTruthy()
    expect(event.context.logger).toBeDefined()

    const warnSpy = vi.spyOn(event.context.logger!, 'warn')
    await expect(authenticateApiRequest(event, vi.fn())).rejects.toMatchObject({ statusCode: 401 })
    expect(warnSpy).toHaveBeenCalledWith(
      expect.objectContaining({ path: '/api/files', statusCode: 401 }),
      'api_auth_denied'
    )
  })

  it('rejects missing or invalid tokens with 401 before touching caches', async () => {
    const event = makeEvent('/api/database?lang=en')
    await expect(authenticateApiRequest(event, vi.fn())).rejects.toMatchObject({ statusCode: 401 })

    const badVerify = vi.fn().mockRejectedValue(new Error('expired'))
    await expect(
      authenticateApiRequest(makeEvent('/api/database', { authorization: 'Bearer bad' }), badVerify)
    ).rejects.toMatchObject({ statusCode: 401 })
  })

  it('rejects unverified email accounts with 403', async () => {
    const verifyUnverified = vi.fn().mockResolvedValue(makeDecodedToken({ email_verified: false }))
    await expect(
      verifyAuthorizedUser('Bearer token', ['user@example.com'], verifyUnverified)
    ).rejects.toMatchObject({ statusCode: 403 })
  })

  it('rejects valid verified tokens outside ALLOWED_EMAILS or empty allowlist with 403', async () => {
    const verifyIntruder = vi
      .fn()
      .mockResolvedValue(makeDecodedToken({ email: 'intruder@evil.com', email_verified: true }))
    await expect(
      authenticateApiRequest(
        makeEvent('/api/database', { authorization: 'Bearer valid' }),
        verifyIntruder
      )
    ).rejects.toMatchObject({ statusCode: 403 })

    const verifyUser = vi.fn().mockResolvedValue(makeDecodedToken())
    await expect(verifyAuthorizedUser('Bearer valid', [], verifyUser)).rejects.toMatchObject({
      statusCode: 403,
    })
  })

  it('attaches normalized AuthUser and restricts admin routes', async () => {
    const verifyUser = vi.fn().mockResolvedValue(makeDecodedToken({ email: 'User@Example.com' }))
    const event = makeEvent('/api/me', { authorization: 'Bearer good-token' })
    await authenticateApiRequest(event, verifyUser)

    expect(event.context.auth).toMatchObject({
      uid: 'user-123',
      email: 'user@example.com',
      email_verified: true,
    })
    expect(event.context.idToken).toBe('good-token')
    expect(meHandler(event)).toEqual({
      email: 'user@example.com',
      isAdmin: false,
      canEditAlbums: true,
    })

    const adminEvent = makeEvent('/api/me', {
      authorization: 'Bearer admin-token',
    })
    const verifyAdmin = vi.fn().mockResolvedValue(makeDecodedToken({ email: 'Admin@Example.com' }))
    await authenticateApiRequest(adminEvent, verifyAdmin)
    expect(meHandler(adminEvent)).toEqual({
      email: 'admin@example.com',
      isAdmin: true,
      canEditAlbums: true,
    })

    expect(() => assertAdminUser(event.context.auth, 'admin@example.com')).toThrowError(
      /Admin access required/
    )
    expect(() =>
      assertAdminUser(
        { uid: 'a', email: 'admin@example.com', email_verified: true },
        'ADMIN@EXAMPLE.COM'
      )
    ).not.toThrow()
  })

  it('mints and verifies __ps_media session cookies only on GET /api/media/*', async () => {
    const verifyUser = vi.fn().mockResolvedValue(makeDecodedToken({ email: 'User@Example.com' }))
    const loginEvent = makeEvent('/api/auth/session', {
      method: 'POST',
      authorization: 'Bearer id-tok-123',
    })
    await authenticateApiRequest(loginEvent, verifyUser)
    const minted = sessionPostHandler(loginEvent)
    expect(minted).toEqual({ authenticated: true, email: 'user@example.com' })

    const setCookieHeader = loginEvent.node.res.getHeader('set-cookie')
    expect(String(setCookieHeader)).toContain(`${MEDIA_COOKIE_NAME}=`)

    const cookieVal = createMediaSessionCookieValue(
      { uid: 'u1', email: 'user@example.com', email_verified: true },
      'id-tok-123',
      'test-session-secret'
    )
    const mediaEvent = makeEvent('/api/media/' + 'a'.repeat(40), {
      method: 'GET',
      cookie: `${MEDIA_COOKIE_NAME}=${encodeURIComponent(cookieVal)}`,
    })
    await authenticateApiRequest(mediaEvent, vi.fn())
    expect(mediaEvent.context.auth?.email).toBe('user@example.com')
    expect(mediaEvent.context.idToken).toBe('id-tok-123')

    // Cookie must NOT authenticate JSON or mutating endpoints
    const mutationWithCookie = makeEvent('/api/albums', {
      method: 'POST',
      cookie: `${MEDIA_COOKIE_NAME}=${encodeURIComponent(cookieVal)}`,
    })
    await expect(authenticateApiRequest(mutationWithCookie, vi.fn())).rejects.toMatchObject({
      statusCode: 401,
    })

    // Expired or tampered cookies fail with 401
    const expiredCookie = createMediaSessionCookieValue(
      { uid: 'u1', email: 'user@example.com', email_verified: true },
      'id-tok-123',
      'test-session-secret',
      -10
    )
    expect(() =>
      verifyMediaSessionCookieValue(expiredCookie, ['user@example.com'], 'test-session-secret')
    ).toThrowError(/expired/)
    expect(() =>
      verifyMediaSessionCookieValue(
        `${cookieVal}tamper`,
        ['user@example.com'],
        'test-session-secret'
      )
    ).toThrowError(/Invalid media session signature/)

    const logoutEvent = makeEvent('/api/auth/session', { method: 'DELETE' })
    expect(sessionDeleteHandler(logoutEvent)).toEqual({ authenticated: false })
  })

  it('clamps __ps_media TTL to Firebase JWT exp and persists .session-secret in mountedVolumePath', () => {
    const makeJwt = (expSec: number) => {
      const header = Buffer.from(JSON.stringify({ alg: 'RS256' })).toString('base64url')
      const payload = Buffer.from(JSON.stringify({ exp: expSec })).toString('base64url')
      return `${header}.${payload}.sig`
    }

    const nowSec = Math.floor(Date.now() / 1000)
    expect(resolveMediaSessionMaxAge('opaque-test-token', 3600)).toBe(3600)
    const clamped = resolveMediaSessionMaxAge(makeJwt(nowSec + 120), 3600)
    expect(clamped).toBeGreaterThan(100)
    expect(clamped).toBeLessThanOrEqual(120)
    expect(() => resolveMediaSessionMaxAge(makeJwt(nowSec - 10), 3600)).toThrowError(/expired/)

    const vol = mkdtempSync(resolve(tmpdir(), 'ps-sec-'))
    tempDirs.push(vol)
    const prevSecret = process.env.PHOTOSPHERE_SESSION_SECRET
    delete process.env.PHOTOSPHERE_SESSION_SECRET
    try {
      const s1 = resolveSessionSecret(undefined, vol)
      const s2 = resolveSessionSecret(undefined, vol)
      expect(s1).toBe(s2)
      expect(s1.length).toBeGreaterThanOrEqual(64)
      const secretPath = resolve(vol, '.session-secret')
      expect(readFileSync(secretPath, 'utf-8').trim()).toBe(s1)
      expect(statSync(secretPath).mode & 0o777).toBe(0o600)
    } finally {
      if (prevSecret !== undefined) process.env.PHOTOSPHERE_SESSION_SECRET = prevSecret
    }
  })
})

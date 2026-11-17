import { IncomingMessage, ServerResponse } from 'node:http'
import { Socket } from 'node:net'
import { createEvent, type H3Event } from 'h3'
import type { DecodedIdToken } from 'firebase-admin/auth'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authenticateApiRequest } from '../../server/middleware/auth'
import {
  assertAdminUser,
  extractBearerToken,
  normalizeAllowedEmails,
  verifyAuthorizedUser,
} from '../../server/services/auth.service'
import { setMockRuntimeConfig } from '../nuxt-imports-stub'

const makeEvent = (path: string, authorization?: string): H3Event => {
  const req = new IncomingMessage(new Socket())
  req.url = path
  req.method = 'GET'
  if (authorization) {
    req.headers.authorization = authorization
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

describe('Server Auth Middleware & Email Allowlist', () => {
  beforeEach(() => {
    setMockRuntimeConfig({
      auth: {
        allowedEmails: ['user@example.com', 'admin@example.com'],
        adminEmail: 'admin@example.com',
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

  it('allows /api/healthz publicly without Bearer token', async () => {
    const verifyFn = vi.fn()
    const event = makeEvent('/api/healthz')
    await authenticateApiRequest(event, verifyFn)
    expect(verifyFn).not.toHaveBeenCalled()
  })

  it('rejects missing or invalid tokens with 401 before touching caches', async () => {
    const event = makeEvent('/api/files?page=1')
    await expect(authenticateApiRequest(event, vi.fn())).rejects.toMatchObject({ statusCode: 401 })

    const badVerify = vi.fn().mockRejectedValue(new Error('expired'))
    await expect(
      authenticateApiRequest(makeEvent('/api/img/thumbnails/a.jpg', 'Bearer bad'), badVerify)
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
      authenticateApiRequest(makeEvent('/api/files', 'Bearer valid'), verifyIntruder)
    ).rejects.toMatchObject({ statusCode: 403 })

    // Fails closed when ALLOWED_EMAILS is empty
    const verifyUser = vi.fn().mockResolvedValue(makeDecodedToken())
    await expect(verifyAuthorizedUser('Bearer valid', [], verifyUser)).rejects.toMatchObject({
      statusCode: 403,
    })
  })

  it('attaches normalized AuthUser for verified allowlisted users and restricts admin routes', async () => {
    const verifyUser = vi.fn().mockResolvedValue(makeDecodedToken({ email: 'User@Example.com' }))
    const event = makeEvent('/api/files', 'Bearer good-token')
    await authenticateApiRequest(event, verifyUser)

    expect(event.context.auth).toMatchObject({
      uid: 'user-123',
      email: 'user@example.com',
      email_verified: true,
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
})

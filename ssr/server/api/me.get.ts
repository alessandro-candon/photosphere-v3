import { createError, defineEventHandler } from 'h3'
import { useRuntimeConfig } from '#imports'

export default defineEventHandler((event) => {
  const auth = event.context.auth
  if (!auth?.email) {
    throw createError({
      statusCode: 401,
      statusMessage: 'Unauthorized: Missing authenticated user',
    })
  }

  const cfg = useRuntimeConfig(event)
  const email = auth.email.trim().toLowerCase()
  const adminEmail = (cfg.auth?.adminEmail || '').trim().toLowerCase()
  const isAdmin = Boolean(adminEmail && email === adminEmail)

  return {
    email,
    isAdmin,
    canEditAlbums: true,
  }
})

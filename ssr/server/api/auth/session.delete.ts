import { defineEventHandler, deleteCookie } from 'h3'
import { MEDIA_COOKIE_NAME } from '../../services/auth.service'

export default defineEventHandler((event) => {
  deleteCookie(event, MEDIA_COOKIE_NAME, {
    httpOnly: true,
    sameSite: 'lax',
    path: '/api/media',
    secure: process.env.NODE_ENV === 'production',
  })

  return {
    authenticated: false,
  }
})

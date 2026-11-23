import { defineEventHandler } from 'h3'

export default defineEventHandler(() => ({
  status: 'ok',
  service: 'photosphere-ssr',
  timestamp: new Date().toISOString(),
}))

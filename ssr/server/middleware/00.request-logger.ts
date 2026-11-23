import { randomUUID } from 'node:crypto'
import { defineEventHandler, getHeader, setHeader, type H3Event } from 'h3'
import { createRequestLogger } from '../services/logger.service'

export const attachRequestLogger = (event: H3Event): void => {
  if (!event.context.requestId) {
    const incomingId = getHeader(event, 'x-request-id')
    const traceContext = getHeader(event, 'x-cloud-trace-context')
    const requestId = incomingId?.trim() || randomUUID()
    event.context.requestId = requestId
    event.context.logger = createRequestLogger(requestId, traceContext)
    setHeader(event, 'x-request-id', requestId)

    const startedAt = Date.now()
    const res = event.node?.res
    if (res && typeof res.on === 'function') {
      res.on('finish', () => {
        const path = (event.path || event.node?.req?.url || '').split('?')[0] || ''
        if (!path.startsWith('/api/')) {
          return
        }
        const method = event.method || event.node?.req?.method || 'GET'
        const payload = {
          method,
          path,
          statusCode: res.statusCode,
          durationMs: Date.now() - startedAt,
          userEmail: event.context.auth?.email,
        }
        if (path === '/api/healthz' || path === '/api/readyz') {
          event.context.logger?.debug(payload, 'http_request_completed')
        } else {
          event.context.logger?.info(payload, 'http_request_completed')
        }
      })
    }
  }
}

export default defineEventHandler((event) => {
  attachRequestLogger(event)
})

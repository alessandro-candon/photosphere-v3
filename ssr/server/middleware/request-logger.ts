import { randomUUID } from 'node:crypto'
import { defineEventHandler, getHeader, setHeader } from 'h3'
import { createRequestLogger } from '../services/logger.service'

export default defineEventHandler((event) => {
  if (!event.context.requestId) {
    const incomingId = getHeader(event, 'x-request-id')
    const traceContext = getHeader(event, 'x-cloud-trace-context')
    const requestId = incomingId?.trim() || randomUUID()
    event.context.requestId = requestId
    event.context.logger = createRequestLogger(requestId, traceContext)
    setHeader(event, 'x-request-id', requestId)
  }
})

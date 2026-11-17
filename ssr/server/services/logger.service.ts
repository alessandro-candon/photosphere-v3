import pino, { type Logger } from 'pino'
import type { H3Event } from 'h3'

const isProduction = process.env.NODE_ENV === 'production'

export const logger: Logger = pino(
  {
    level: process.env.LOG_LEVEL || (isProduction ? 'info' : 'debug'),
    redact: {
      paths: [
        'authorization',
        'req.headers.authorization',
        'headers.authorization',
        'idToken',
        'token',
        '*.idToken',
        '*.token',
      ],
      censor: '[REDACTED]',
    },
    formatters: {
      level(label) {
        return { severity: label.toUpperCase() }
      },
    },
  },
  isProduction
    ? undefined
    : pino.transport({
        target: 'pino-pretty',
        options: {
          colorize: true,
          translateTime: 'SYS:standard',
          ignore: 'pid,hostname',
        },
      })
)

export const createRequestLogger = (requestId: string, traceContext?: string): Logger =>
  logger.child({
    requestId,
    ...(traceContext ? { traceContext } : {}),
  })

export const getEventLogger = (event?: H3Event | null): Logger => {
  if (event?.context?.logger) {
    return event.context.logger
  }
  return logger
}

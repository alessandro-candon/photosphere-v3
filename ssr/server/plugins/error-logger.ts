import { defineNitroPlugin } from 'nitropack/runtime'
import { logger } from '../services/logger.service'

export default defineNitroPlugin((nitroApp) => {
  nitroApp.hooks.hook('error', (error, { event }) => {
    const reqLogger = event?.context?.logger || logger
    reqLogger.error(
      {
        err:
          error instanceof Error ? { message: error.message, stack: error.stack } : String(error),
        path: event?.path,
      },
      'unhandled_nitro_error'
    )
  })
})

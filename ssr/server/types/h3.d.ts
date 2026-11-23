import type { Logger } from 'pino'
import type { AuthUser } from './auth'

declare module 'h3' {
  interface H3EventContext {
    auth?: AuthUser
    idToken?: string
    requestId?: string
    logger?: Logger
  }
}

export {}

import { existsSync, readFileSync } from 'node:fs'
import { cert, getApps, initializeApp, type ServiceAccount } from 'firebase-admin/app'
import { isOfflineTestOrTypecheck, loadPhotosphereConfig } from '../utils/photosphere-config'
import { logger } from './logger.service'

let hasServiceAccountCredential = false

export const hasFirebaseAdminCredentials = (): boolean => hasServiceAccountCredential

const resolveProjectId = (): string | undefined => {
  const fromEnv = (process.env.FIREBASE_PROJECT_ID || '').trim()
  if (fromEnv) {
    return fromEnv
  }
  if (isOfflineTestOrTypecheck()) {
    return undefined
  }
  try {
    return loadPhotosphereConfig()?.firebase.project_id || undefined
  } catch {
    return undefined
  }
}

const loadServiceAccount = (raw: string): ServiceAccount | null => {
  const trimmed = raw.trim()
  if (!trimmed) {
    return null
  }
  try {
    if (trimmed.startsWith('{')) {
      return JSON.parse(trimmed) as ServiceAccount
    }
    if (existsSync(trimmed)) {
      return JSON.parse(readFileSync(trimmed, 'utf-8')) as ServiceAccount
    }
  } catch (error) {
    logger.warn({ err: String(error) }, 'firebase_service_account_parse_failed')
  }
  return null
}

export const ensureFirebaseAdminInitialized = (): void => {
  if (getApps().length > 0) {
    return
  }
  const projectId = resolveProjectId()
  const rawKey = process.env.FIREBASE_SERVICE_ACCOUNT_KEY || ''
  const serviceAccount = loadServiceAccount(rawKey)

  if (serviceAccount) {
    initializeApp({
      credential: cert(serviceAccount),
      ...(projectId ? { projectId } : {}),
    })
    hasServiceAccountCredential = true
    logger.info({ projectId }, 'firebase_admin_initialized_service_account')
    return
  }

  hasServiceAccountCredential = false
  initializeApp(projectId ? { projectId } : undefined)
  logger.info({ projectId }, 'firebase_admin_initialized_public_jwt')
}

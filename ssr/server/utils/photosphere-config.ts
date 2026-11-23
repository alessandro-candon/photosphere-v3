import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

export type StorageClass = 'STANDARD' | 'ARCHIVE'

export interface PhotosphereConfig {
  version: 1
  gcp: {
    project_id: string
    location: string
  }
  storage: {
    media_bucket: string
    media_storage_class: StorageClass
    data_bucket: string
    data_storage_class: StorageClass
  }
  firebase: {
    project_id: string
    app_id: string
    api_key: string
    auth_domain: string
    storage_bucket: string
    messaging_sender_id: string
  }
  auth: {
    allowed_emails: string[]
    admin_email: string
  }
  pipeline: {
    default_lang: string
    target_lang: string
  }
}

const DEFAULT_CONFIG_FILENAME = 'photosphere.config.json'
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

const assertRecord = (value: unknown, label: string): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`Invalid photosphere.config.json: '${label}' must be an object.`)
  }
  return value as Record<string, unknown>
}

const assertNonEmptyString = (value: unknown, label: string): string => {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(`Invalid photosphere.config.json: '${label}' must be a non-empty string.`)
  }
  return value.trim()
}

const assertStorageClass = (value: unknown, label: string): StorageClass => {
  if (value !== 'STANDARD' && value !== 'ARCHIVE') {
    throw new Error(`Invalid photosphere.config.json: '${label}' must be STANDARD or ARCHIVE.`)
  }
  return value
}

export const isOfflineTestOrTypecheck = (): boolean =>
  Boolean(
    process.env.VITEST ||
    process.env.NODE_ENV === 'test' ||
    process.env.NUXT_TYPECHECK ||
    process.env.npm_lifecycle_event === 'type-check' ||
    process.argv.some((arg) => arg === 'typecheck' || arg === 'prepare')
  )

export const resolvePhotosphereConfigPath = (explicitPath?: string): string | null => {
  const candidates: string[] = []
  if (explicitPath) {
    candidates.push(resolve(explicitPath))
  } else if (process.env.PHOTOSPHERE_CONFIG_PATH) {
    candidates.push(resolve(process.env.PHOTOSPHERE_CONFIG_PATH))
  } else {
    candidates.push(
      resolve(process.cwd(), DEFAULT_CONFIG_FILENAME),
      resolve(process.cwd(), '..', DEFAULT_CONFIG_FILENAME)
    )
  }
  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      return candidate
    }
  }
  return null
}

export const validatePhotosphereConfig = (raw: unknown): PhotosphereConfig => {
  const root = assertRecord(raw, 'root')
  if (root.version !== 1) {
    throw new Error("Invalid photosphere.config.json: 'version' must equal 1.")
  }

  const gcp = assertRecord(root.gcp, 'gcp')
  const storage = assertRecord(root.storage, 'storage')
  const firebase = assertRecord(root.firebase, 'firebase')
  const auth = assertRecord(root.auth, 'auth')
  const pipeline = assertRecord(root.pipeline, 'pipeline')

  if (!Array.isArray(auth.allowed_emails) || auth.allowed_emails.length === 0) {
    throw new Error("Invalid photosphere.config.json: 'auth.allowed_emails' must be non-empty.")
  }
  const allowedEmails = auth.allowed_emails.map((item, idx) => {
    const email = assertNonEmptyString(item, `auth.allowed_emails[${idx}]`).toLowerCase()
    if (!EMAIL_RE.test(email)) {
      throw new Error(`Invalid photosphere.config.json: invalid email '${email}'.`)
    }
    return email
  })
  const adminEmail = assertNonEmptyString(auth.admin_email, 'auth.admin_email').toLowerCase()
  if (!EMAIL_RE.test(adminEmail)) {
    throw new Error(`Invalid photosphere.config.json: invalid admin_email '${adminEmail}'.`)
  }

  return {
    version: 1,
    gcp: {
      project_id: assertNonEmptyString(gcp.project_id, 'gcp.project_id'),
      location: assertNonEmptyString(gcp.location, 'gcp.location'),
    },
    storage: {
      media_bucket: assertNonEmptyString(storage.media_bucket, 'storage.media_bucket'),
      media_storage_class: assertStorageClass(
        storage.media_storage_class,
        'storage.media_storage_class'
      ),
      data_bucket: assertNonEmptyString(storage.data_bucket, 'storage.data_bucket'),
      data_storage_class: assertStorageClass(
        storage.data_storage_class,
        'storage.data_storage_class'
      ),
    },
    firebase: {
      project_id: assertNonEmptyString(firebase.project_id, 'firebase.project_id'),
      app_id: assertNonEmptyString(firebase.app_id, 'firebase.app_id'),
      api_key: assertNonEmptyString(firebase.api_key, 'firebase.api_key'),
      auth_domain: assertNonEmptyString(firebase.auth_domain, 'firebase.auth_domain'),
      storage_bucket: assertNonEmptyString(firebase.storage_bucket, 'firebase.storage_bucket'),
      messaging_sender_id: assertNonEmptyString(
        firebase.messaging_sender_id,
        'firebase.messaging_sender_id'
      ),
    },
    auth: {
      allowed_emails: allowedEmails,
      admin_email: adminEmail,
    },
    pipeline: {
      default_lang: assertNonEmptyString(pipeline.default_lang, 'pipeline.default_lang'),
      target_lang: assertNonEmptyString(pipeline.target_lang, 'pipeline.target_lang'),
    },
  }
}

export const loadPhotosphereConfig = (explicitPath?: string): PhotosphereConfig => {
  const resolved = resolvePhotosphereConfigPath(explicitPath)
  if (!resolved) {
    throw new Error(
      'Missing photosphere.config.json. Run `make init` to provision the environment before starting SSR.'
    )
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(readFileSync(resolved, 'utf-8'))
  } catch (error) {
    throw new Error(`Failed to parse ${resolved}: ${String(error)}`)
  }
  return validatePhotosphereConfig(parsed)
}

export const applyConfigToProcessEnv = (config: PhotosphereConfig): void => {
  const defaults: Record<string, string> = {
    FIREBASE_API_KEY: config.firebase.api_key,
    FIREBASE_AUTH_DOMAIN: config.firebase.auth_domain,
    FIREBASE_PROJECT_ID: config.firebase.project_id,
    FIREBASE_STORAGE_BUCKET: config.firebase.storage_bucket,
    FIREBASE_APP_ID: config.firebase.app_id,
    PHOTOSPHERE_MEDIA_BUCKET: config.storage.media_bucket,
    PHOTOSPHERE_DATA_BUCKET: config.storage.data_bucket,
    ALLOWED_EMAILS: config.auth.allowed_emails.join(','),
    ADMIN_EMAIL: config.auth.admin_email,
    NUXT_PUBLIC_DEFAULT_LANG: config.pipeline.default_lang,
  }
  for (const [key, value] of Object.entries(defaults)) {
    if (!process.env[key]) {
      process.env[key] = value
    }
  }
}

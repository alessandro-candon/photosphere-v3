import { resolve } from 'node:path'
import { defineNitroPlugin, useRuntimeConfig } from 'nitropack/runtime'
import { normalizeAllowedEmails } from '#shared/constants'
import {
  applyConfigToProcessEnv,
  isOfflineTestOrTypecheck,
  loadPhotosphereConfig,
} from '../utils/photosphere-config'

export default defineNitroPlugin((nitroApp) => {
  if (isOfflineTestOrTypecheck()) {
    return
  }

  const config = loadPhotosphereConfig()
  applyConfigToProcessEnv(config)

  // Hydrate the mutable per-request runtimeConfig clone instead of mutating
  // Nitro's deeply frozen _sharedRuntimeConfig.
  nitroApp.hooks.hook('request', (event) => {
    const runtimeConfig = useRuntimeConfig(event)
    runtimeConfig.public.firebase.apiKey =
      process.env.FIREBASE_API_KEY ||
      runtimeConfig.public.firebase.apiKey ||
      config.firebase.api_key
    runtimeConfig.public.firebase.authDomain =
      process.env.FIREBASE_AUTH_DOMAIN ||
      runtimeConfig.public.firebase.authDomain ||
      config.firebase.auth_domain
    runtimeConfig.public.firebase.projectId =
      process.env.FIREBASE_PROJECT_ID ||
      runtimeConfig.public.firebase.projectId ||
      config.firebase.project_id
    runtimeConfig.public.firebase.storageBucket =
      process.env.FIREBASE_STORAGE_BUCKET ||
      process.env.PHOTOSPHERE_MEDIA_BUCKET ||
      runtimeConfig.public.firebase.storageBucket ||
      config.firebase.storage_bucket
    runtimeConfig.public.firebase.appId =
      process.env.FIREBASE_APP_ID || runtimeConfig.public.firebase.appId || config.firebase.app_id
    runtimeConfig.public.defaultLang =
      process.env.NUXT_PUBLIC_DEFAULT_LANG ||
      runtimeConfig.public.defaultLang ||
      config.pipeline.default_lang ||
      'en'

    runtimeConfig.storage.mediaBucket =
      process.env.PHOTOSPHERE_MEDIA_BUCKET ||
      runtimeConfig.storage.mediaBucket ||
      config.storage.media_bucket
    runtimeConfig.storage.dataBucket =
      process.env.PHOTOSPHERE_DATA_BUCKET ||
      runtimeConfig.storage.dataBucket ||
      config.storage.data_bucket
    runtimeConfig.storage.mountedVolumePath =
      process.env.PHOTOSPHERE_MOUNTED_VOLUME_PATH ||
      runtimeConfig.storage.mountedVolumePath ||
      resolve(process.cwd(), '.photosphere-cache')

    runtimeConfig.auth.allowedEmails = process.env.ALLOWED_EMAILS
      ? normalizeAllowedEmails(process.env.ALLOWED_EMAILS)
      : runtimeConfig.auth.allowedEmails.length > 0
        ? runtimeConfig.auth.allowedEmails
        : [...config.auth.allowed_emails]
    runtimeConfig.auth.adminEmail = (
      process.env.ADMIN_EMAIL ||
      runtimeConfig.auth.adminEmail ||
      config.auth.admin_email
    )
      .trim()
      .toLowerCase()
    runtimeConfig.auth.sessionSecret =
      process.env.PHOTOSPHERE_SESSION_SECRET || runtimeConfig.auth.sessionSecret || ''
  })
})

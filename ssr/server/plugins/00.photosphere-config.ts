import { defineNitroPlugin, useRuntimeConfig } from 'nitropack/runtime'
import {
  applyConfigToProcessEnv,
  isOfflineTestOrTypecheck,
  loadPhotosphereConfig,
} from '../utils/photosphere-config'

export default defineNitroPlugin(() => {
  if (isOfflineTestOrTypecheck()) {
    return
  }
  const config = loadPhotosphereConfig()
  applyConfigToProcessEnv(config)

  const runtimeConfig = useRuntimeConfig()
  runtimeConfig.public.firebase.apiKey ||= config.firebase.api_key
  runtimeConfig.public.firebase.authDomain ||= config.firebase.auth_domain
  runtimeConfig.public.firebase.projectId ||= config.firebase.project_id
  runtimeConfig.public.firebase.storageBucket ||= config.firebase.storage_bucket
  runtimeConfig.public.firebase.appId ||= config.firebase.app_id
  runtimeConfig.public.defaultLang ||= config.pipeline.default_lang

  runtimeConfig.storage.mediaBucket ||= config.storage.media_bucket
  runtimeConfig.storage.dataBucket ||= config.storage.data_bucket
  if (!runtimeConfig.auth.allowedEmails.length) {
    runtimeConfig.auth.allowedEmails = [...config.auth.allowed_emails]
  }
  runtimeConfig.auth.adminEmail ||= config.auth.admin_email
})

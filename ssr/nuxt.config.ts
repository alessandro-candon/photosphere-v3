import { defineNuxtConfig } from 'nuxt/config'
import {
  isOfflineTestOrTypecheck,
  loadPhotosphereConfig,
  type PhotosphereConfig,
} from './server/utils/photosphere-config'

const parseAllowedEmails = (raw: string | undefined): string[] =>
  (raw || '')
    .split(',')
    .map((email) => email.trim().toLowerCase())
    .filter(Boolean)

const fileConfig: PhotosphereConfig | null = isOfflineTestOrTypecheck()
  ? null
  : loadPhotosphereConfig()

export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: false },
  modules: ['@pinia/nuxt'],
  css: ['@quasar/extras/material-icons/material-icons.css', 'quasar/dist/quasar.css'],
  build: {
    transpile: ['quasar'],
  },
  typescript: {
    strict: true,
    typeCheck: false,
  },
  runtimeConfig: {
    public: {
      firebase: {
        apiKey: process.env.FIREBASE_API_KEY || fileConfig?.firebase.api_key || '',
        authDomain: process.env.FIREBASE_AUTH_DOMAIN || fileConfig?.firebase.auth_domain || '',
        projectId: process.env.FIREBASE_PROJECT_ID || fileConfig?.firebase.project_id || '',
        storageBucket:
          process.env.FIREBASE_STORAGE_BUCKET ||
          process.env.PHOTOSPHERE_MEDIA_BUCKET ||
          fileConfig?.firebase.storage_bucket ||
          '',
        appId: process.env.FIREBASE_APP_ID || fileConfig?.firebase.app_id || '',
      },
      defaultLang:
        process.env.NUXT_PUBLIC_DEFAULT_LANG || fileConfig?.pipeline.default_lang || 'en',
    },
    storage: {
      mediaBucket: process.env.PHOTOSPHERE_MEDIA_BUCKET || fileConfig?.storage.media_bucket || '',
      dataBucket: process.env.PHOTOSPHERE_DATA_BUCKET || fileConfig?.storage.data_bucket || '',
      mountedVolumePath: process.env.PHOTOSPHERE_MOUNTED_VOLUME_PATH || '/mnt/photosphere',
    },
    auth: {
      allowedEmails: process.env.ALLOWED_EMAILS
        ? parseAllowedEmails(process.env.ALLOWED_EMAILS)
        : (fileConfig?.auth.allowed_emails ?? []),
      adminEmail: (process.env.ADMIN_EMAIL || fileConfig?.auth.admin_email || '')
        .trim()
        .toLowerCase(),
    },
    thumbnailCache: {
      directoryName: process.env.PHOTOSPHERE_THUMBNAIL_CACHE_DIRECTORY || 'thumbnail-cache',
      ttlMs: Number(process.env.PHOTOSPHERE_THUMBNAIL_CACHE_TTL_MS) || 30 * 24 * 60 * 60 * 1000,
      maxObjectBytes:
        Number(process.env.PHOTOSPHERE_THUMBNAIL_CACHE_MAX_OBJECT_BYTES) || 5 * 1024 * 1024,
      maxCacheBytes:
        Number(process.env.PHOTOSPHERE_THUMBNAIL_CACHE_MAX_CACHE_BYTES) || 2 * 1024 * 1024 * 1024,
    },
    mediaCache: {
      directoryName: process.env.PHOTOSPHERE_MEDIA_CACHE_DIRECTORY || 'media-cache',
      ttlMs: Number(process.env.PHOTOSPHERE_MEDIA_CACHE_TTL_MS) || 12 * 60 * 60 * 1000,
      maxObjectBytes:
        Number(process.env.PHOTOSPHERE_MEDIA_CACHE_MAX_OBJECT_BYTES) || 100 * 1024 * 1024,
      maxCacheBytes:
        Number(process.env.PHOTOSPHERE_MEDIA_CACHE_MAX_CACHE_BYTES) || 2 * 1024 * 1024 * 1024,
    },
    database: {
      jsonFileName: 'photosphere_database_cloud.json',
      labelsJsonFileName: 'photosphere_image_labelling_database_cloud.json',
      captionsJsonFileName: 'photosphere_image_caption_database_cloud.json',
      albumsJsonFileName: 'photosphere_albums.json',
    },
  },
})

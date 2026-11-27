export interface MockRuntimeConfig {
  public: {
    defaultLang: string
    firebase: {
      apiKey: string
      authDomain: string
      projectId: string
      storageBucket: string
      appId: string
    }
  }
  storage: {
    mediaBucket: string
    dataBucket: string
    mountedVolumePath: string
  }
  mediaCache: {
    directoryName: string
    maxCacheBytes: number
    maxCacheableVideoBytes: number
  }
  location: {
    nominatimBaseUrl: string
    minIntervalMs: number
    timeoutMs: number
    userAgent: string
  }
  auth: {
    allowedEmails: string[]
    adminEmail: string
    sessionSecret?: string
  }
  database: {
    jsonFileName: string
    labelsJsonFileName: string
    captionsJsonFileName: string
    albumsJsonFileName: string
  }
}

export interface MockRuntimeConfigOverride {
  public?: Partial<MockRuntimeConfig['public']>
  storage?: Partial<MockRuntimeConfig['storage']>
  mediaCache?: Partial<MockRuntimeConfig['mediaCache']>
  location?: Partial<MockRuntimeConfig['location']>
  auth?: Partial<MockRuntimeConfig['auth']>
  database?: Partial<MockRuntimeConfig['database']>
}

let currentConfig: MockRuntimeConfig = {
  public: {
    defaultLang: 'en',
    firebase: {
      apiKey: '',
      authDomain: '',
      projectId: '',
      storageBucket: '',
      appId: '',
    },
  },
  storage: {
    mediaBucket: process.env.PHOTOSPHERE_MEDIA_BUCKET || 'test-media-archive',
    dataBucket: process.env.PHOTOSPHERE_DATA_BUCKET || 'test-data-standard',
    mountedVolumePath: process.env.PHOTOSPHERE_MOUNTED_VOLUME_PATH || '/tmp/photosphere-test',
  },
  mediaCache: {
    directoryName: 'media',
    maxCacheBytes: 64 * 1024 * 1024,
    maxCacheableVideoBytes: 16 * 1024 * 1024,
  },
  location: {
    nominatimBaseUrl: 'https://nominatim.openstreetmap.org',
    minIntervalMs: 0,
    timeoutMs: 5000,
    userAgent: 'Photosphere-Test/1.0',
  },
  auth: {
    allowedEmails: (process.env.ALLOWED_EMAILS || '')
      .split(',')
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean),
    adminEmail: (process.env.ADMIN_EMAIL || '').trim().toLowerCase(),
    sessionSecret: 'test-session-secret',
  },
  database: {
    jsonFileName: 'photosphere_database_cloud.json',
    labelsJsonFileName: 'photosphere_image_labelling_database_cloud.json',
    captionsJsonFileName: 'photosphere_image_caption_database_cloud.json',
    albumsJsonFileName: 'photosphere_albums.json',
  },
}

let mockNuxtApp: Record<string, unknown> = {}
let mockRoute: { path: string; query: Record<string, unknown>; params: Record<string, unknown> } = {
  path: '/',
  query: {},
  params: {},
}
let navigateToHandler: (to: unknown) => Promise<void> | void = async () => {}

export const setMockRuntimeConfig = (next: MockRuntimeConfigOverride): void => {
  currentConfig = {
    public: {
      ...currentConfig.public,
      ...next.public,
      firebase: {
        ...currentConfig.public.firebase,
        ...next.public?.firebase,
      },
    },
    storage: { ...currentConfig.storage, ...next.storage },
    mediaCache: { ...currentConfig.mediaCache, ...next.mediaCache },
    location: { ...currentConfig.location, ...next.location },
    auth: { ...currentConfig.auth, ...next.auth },
    database: { ...currentConfig.database, ...next.database },
  }
}

export const setMockNuxtApp = (next: Record<string, unknown>): void => {
  mockNuxtApp = next
}

export const setMockRoute = (
  next: Partial<{ path: string; query: Record<string, unknown>; params: Record<string, unknown> }>
): void => {
  mockRoute = { ...mockRoute, ...next }
}

export const setMockNavigateTo = (fn: (to: unknown) => Promise<void> | void): void => {
  navigateToHandler = fn
}

export const useRuntimeConfig = () => currentConfig
export const useNuxtApp = () => mockNuxtApp
export const useRoute = () => mockRoute
export const navigateTo = (to: unknown) => navigateToHandler(to)
export const defineNuxtRouteMiddleware = <T>(fn: T): T => fn

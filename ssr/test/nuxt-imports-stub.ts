export interface MockRuntimeConfig {
  public: {
    defaultLang: string
  }
  storage: {
    mediaBucket: string
    dataBucket: string
    mountedVolumePath: string
  }
  auth: {
    allowedEmails: string[]
    adminEmail: string
  }
}

let currentConfig: MockRuntimeConfig = {
  public: {
    defaultLang: 'en',
  },
  storage: {
    mediaBucket: process.env.PHOTOSPHERE_MEDIA_BUCKET || 'test-media-archive',
    dataBucket: process.env.PHOTOSPHERE_DATA_BUCKET || 'test-data-standard',
    mountedVolumePath: process.env.PHOTOSPHERE_MOUNTED_VOLUME_PATH || '/tmp/photosphere-test',
  },
  auth: {
    allowedEmails: (process.env.ALLOWED_EMAILS || '')
      .split(',')
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean),
    adminEmail: (process.env.ADMIN_EMAIL || '').trim().toLowerCase(),
  },
}

export const setMockRuntimeConfig = (next: Partial<MockRuntimeConfig>): void => {
  currentConfig = {
    public: { ...currentConfig.public, ...next.public },
    storage: { ...currentConfig.storage, ...next.storage },
    auth: { ...currentConfig.auth, ...next.auth },
  }
}

export const useRuntimeConfig = () => currentConfig

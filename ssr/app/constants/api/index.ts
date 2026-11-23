export const API_ENDPOINTS = {
  healthz: '/api/healthz',
  readyz: '/api/readyz',
  me: '/api/me',
  authSession: '/api/auth/session',
  database: '/api/database',
  refreshDatabase: '/api/admin/refresh-database',
  files: '/api/files',
  media: '/api/media',
  searchSuggestions: '/api/search/suggestions',
  locationSearch: '/api/location/search',
  albums: '/api/albums',
} as const

export const API_ENDPOINTS = {
  healthz: '/api/healthz',
  readyz: '/api/readyz',
  files: '/api/files',
  albums: '/api/albums',
  searchSuggestions: '/api/search/suggestions',
  locationSearch: '/api/location/search',
  refreshDatabase: '/api/admin/refresh-database',
} as const

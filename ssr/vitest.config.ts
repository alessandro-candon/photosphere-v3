import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'node',
    include: ['test/**/*.test.ts'],
    setupFiles: ['test/setup.ts'],
    coverage: {
      provider: 'v8',
      include: [
        'server/middleware/auth.ts',
        'server/services/auth.service.ts',
        'server/utils/storage-download.ts',
        'server/utils/file-database-cache.ts',
        'server/utils/albums-cache.ts',
      ],
    },
  },
  resolve: {
    alias: {
      '#imports': fileURLToPath(new URL('./test/nuxt-imports-stub.ts', import.meta.url)),
      '~': fileURLToPath(new URL('./app', import.meta.url)),
      '@': fileURLToPath(new URL('./app', import.meta.url)),
    },
  },
})

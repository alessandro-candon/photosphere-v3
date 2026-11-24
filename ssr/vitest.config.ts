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
        'shared/**/*.ts',
        'server/**/*.ts',
        'app/composables/**/*.ts',
        'app/stores/**/*.ts',
      ],
      exclude: ['server/types/**/*.ts'],
    },
  },
  resolve: {
    alias: {
      '#imports': fileURLToPath(new URL('./test/nuxt-imports-stub.ts', import.meta.url)),
      '#shared': fileURLToPath(new URL('./shared', import.meta.url)),
      '~': fileURLToPath(new URL('./app', import.meta.url)),
      '@': fileURLToPath(new URL('./app', import.meta.url)),
      '~~': fileURLToPath(new URL('.', import.meta.url)),
      '@@': fileURLToPath(new URL('.', import.meta.url)),
    },
  },
})

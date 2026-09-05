import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Forward API calls to the FastAPI server so the client needs no CORS setup.
// VITE_PROXY_TARGET lets docker-compose point at the api container instead.
const apiProxy = {
  target: process.env.VITE_PROXY_TARGET || 'http://localhost:8000',
  changeOrigin: true,
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // vitest: a DOM implementation for component tests, describe/it/expect as
  // globals, and jest-dom matchers registered once in the setup file.
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
  },
  server: {
    proxy: {
      '/auth': apiProxy,
      '/tickets': apiProxy,
      '/users': apiProxy,
      '/categories': apiProxy,
      '/health': apiProxy,
    },
  },
})

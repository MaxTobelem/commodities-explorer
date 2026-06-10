import path from 'node:path'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    proxy: {
      // Same-origin in dev: the SPA calls /api, Vite proxies to Django.
      // 127.0.0.1 (not "localhost") sidesteps macOS IPv6 resolution; the
      // default :8001 keeps us clear of :8000, which other local Docker
      // projects may already occupy. Override with VITE_API_TARGET if needed.
      '/api': {
        target: process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
})

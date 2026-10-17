import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The python backend (FastAPI) runs on :8000. Everything under /api is proxied
// there so the frontend never hard-codes a host. Falls back to mock data when down.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, '') },
    },
  },
})

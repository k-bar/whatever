import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The python backend (FastAPI) runs on :8000. Everything under /api is proxied
// there so the frontend never hard-codes a host (ws: the chat socket, GET /ws).
export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        // vendor chunks: a UI change no longer invalidates the (large, rarely changing) map library
        manualChunks: { maplibre: ['maplibre-gl'], motion: ['framer-motion'], react: ['react', 'react-dom'] },
      },
    },
  },
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true, ws: true, rewrite: (p) => p.replace(/^\/api/, '') },
    },
  },
})

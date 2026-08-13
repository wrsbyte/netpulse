import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The API (uvicorn) serves the built SPA in production; in dev we proxy /api to it.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Single-page localhost app served locally — code-splitting buys nothing here.
  build: { outDir: 'dist', chunkSizeWarningLimit: 900 },
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8477' },
  },
})

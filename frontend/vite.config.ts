import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The API is proxied under /api so auth cookies are first-party (same origin as the SPA).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Listen on the local network so phones on the same Wi-Fi can open the app (development only).
    host: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false, xfwd: true },
    },
  },
})

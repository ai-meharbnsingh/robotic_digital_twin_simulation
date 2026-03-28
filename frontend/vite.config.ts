import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8029',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8029',
        ws: true,
      },
    },
  },
})

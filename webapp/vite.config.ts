import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const API_PATHS = ['/assistants', '/bulk', '/extract', '/schema', '/compare', '/health', '/models']

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      API_PATHS.map((path) => [path, { target: 'http://127.0.0.1:8000', changeOrigin: true }]),
    ),
  },
})

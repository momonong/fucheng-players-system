import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  // The server supplies <base> at runtime, so one build works at / and /fucheng/.
  base: './',
  plugins: [react()],
  build: { outDir: process.env.FUCHENG_BUILD_DIR ?? '../src/fucheng/static', emptyOutDir: true },
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})

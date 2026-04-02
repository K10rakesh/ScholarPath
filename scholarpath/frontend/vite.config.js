import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/upload-pdf': 'http://localhost:8000',
      '/analyze': 'http://localhost:8000',
      '/status': 'http://localhost:8000',
      '/results': 'http://localhost:8000',
      '/resolve-citations': 'http://localhost:8000',
      '/citations': 'http://localhost:8000',
      '/verify': 'http://localhost:8000',
      '/verification': 'http://localhost:8000',
      '/generate-roadmap': 'http://localhost:8000',
      '/roadmap': 'http://localhost:8000',
      '/full-pipeline': 'http://localhost:8000',
      '/final-report': 'http://localhost:8000',
      '/demo-papers': 'http://localhost:8000',
    }
  }
})

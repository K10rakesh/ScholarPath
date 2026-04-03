import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/upload-pdf': 'http://localhost:8001',
      '/analyze': 'http://localhost:8001',
      '/status': 'http://localhost:8001',
      '/results': 'http://localhost:8001',
      '/resolve-citations': 'http://localhost:8001',
      '/citations': 'http://localhost:8001',
      '/verify': 'http://localhost:8001',
      '/verification': 'http://localhost:8001',
      '/generate-roadmap': 'http://localhost:8001',
      '/roadmap': 'http://localhost:8001',
      '/full-pipeline': 'http://localhost:8001',
      '/final-report': 'http://localhost:8001',
      '/demo-papers': 'http://localhost:8001',
    }
  }
})

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 5173 is often taken by other course projects, so this app uses its own ports.
    port: 5175,
    strictPort: true,
    // Forward API and profile-picture requests to the FastAPI backend on port 8001.
    proxy: {
      '/api': 'http://localhost:8001',
      '/uploads': 'http://localhost:8001',
    },
  },
})

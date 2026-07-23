import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Static JSON lives in public/api/*.json for Predictions / Leaderboard / Podiumigami.
      // Live What If (+ health probe) hit the local api/ server.
      // Do NOT proxy '/api/predict' — it would steal '/api/predictions_*.json'.
      '/api/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/api/what-if': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve, dirname } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))

// Elasticsearch has security enabled (ELASTIC_PASSWORD in .env) — an
// unauthenticated request 401s, axios treats that as a rejected promise, and
// useElasticPolling reads a rejected promise as "cluster unreachable" and
// falls back to mock data. Without this, dev mode was never actually live
// no matter how healthy the stack was.
function elasticPassword(): string {
  const envPath = resolve(__dirname, '../.env')
  if (existsSync(envPath)) {
    const match = readFileSync(envPath, 'utf-8').match(/^ELASTIC_PASSWORD=(.*)$/m)
    if (match) return match[1].trim()
  }
  return 'meridian123'
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // In dev: /api/* → http://localhost:9200/* (Elasticsearch)
      // On Vercel: requests fail gracefully → mock data fallback
      '/api': {
        target: 'http://localhost:9200',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        auth: `elastic:${elasticPassword()}`,
      },
    },
  },
})

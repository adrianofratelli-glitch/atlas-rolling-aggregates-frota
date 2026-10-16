import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Portas estritas do registro do workspace (5410/8410) e bind em 127.0.0.1, como
// as demais PoVs. Em dev o Vite encaminha a API; em produção o FastAPI serve o dist.
const api = 'http://127.0.0.1:8410'
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1', port: 5410, strictPort: true,
    proxy: { '/api': api, '/eta': api, '/health': api },
  },
  preview: { host: '127.0.0.1', port: 5410, strictPort: true,
    proxy: { '/api': api, '/eta': api, '/health': api } },
})

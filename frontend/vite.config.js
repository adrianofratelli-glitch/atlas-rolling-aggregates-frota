import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Portas estritas do registro do workspace (5410/8410) e bind em 127.0.0.1, como
// as demais PoVs. Em dev o Vite encaminha a API; em produção o FastAPI serve o dist.
const api = `http://127.0.0.1:${process.env.VITE_API_PORT || 8410}`
const porta = Number(process.env.VITE_PORT || 5410)
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1', port: porta, strictPort: true,
    proxy: { '/api': api, '/eta': api, '/health': api },
  },
  preview: { host: '127.0.0.1', port: porta, strictPort: true,
    proxy: { '/api': api, '/eta': api, '/health': api } },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Portas estritas do registro do workspace (5410/8410) e bind em 127.0.0.1, como
// as demais PoVs. Em dev o Vite encaminha a API; em produção o FastAPI serve o dist.
// Para rodar uma segunda instância (ex.: prints): `npm run dev -- --port 5419` e
// `VITE_API_PORT=8419` para apontar o proxy para outra API.
const api = `http://127.0.0.1:${process.env.VITE_API_PORT || 8410}`
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1', port: 5410, strictPort: true,
    proxy: { '/api': api, '/eta': api, '/health': api },
  },
  preview: { host: '127.0.0.1', port: 5410, strictPort: true,
    proxy: { '/api': api, '/eta': api, '/health': api } },
})

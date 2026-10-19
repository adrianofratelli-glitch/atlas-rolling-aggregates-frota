const FORA = 'Backend fora do ar em 127.0.0.1:8410 — rode `make api`.'

async function req(url, opts) {
  let r
  try {
    r = await fetch(url, opts)
  } catch {
    // só a falha de rede significa backend fora do ar
    throw new Error(FORA)
  }
  const corpo = await r.json().catch(() => null)
  if (!r.ok) {
    const msg = corpo?.erro ? `${corpo.erro}${corpo.acao ? ` — ${corpo.acao}` : ''}`
      // 502 sem corpo é o proxy do Vite sem resposta da API; outro 5xx sem JSON é erro inesperado
      : r.status === 502 ? 'A API não respondeu pelo proxy (HTTP 502) — confira `make api`.'
        : r.status >= 500 ? `Erro inesperado no servidor (HTTP ${r.status}).` : `HTTP ${r.status}`
    throw Object.assign(new Error(msg), { status: r.status })
  }
  return corpo ?? {}
}
const qs = (p) => new URLSearchParams(Object.entries(p).filter(([, v]) => v !== '' && v != null)).toString()
export const get = (path, params = {}) => req(`${path}?${qs(params)}`)
export const post = (path, body = {}) => req(path, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
})

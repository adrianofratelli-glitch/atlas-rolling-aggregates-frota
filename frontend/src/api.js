async function req(url, opts) {
  let r
  try {
    r = await fetch(url, opts)
  } catch {
    throw new Error('Backend fora do ar em 127.0.0.1:8410 — rode `make api`.')
  }
  const corpo = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(corpo.erro ? `${corpo.erro}${corpo.acao ? ` — ${corpo.acao}` : ''}` : `HTTP ${r.status}`)
  return corpo
}
const qs = (p) => new URLSearchParams(Object.entries(p).filter(([, v]) => v !== '' && v != null)).toString()
export const get = (path, params = {}) => req(`${path}?${qs(params)}`)
export const post = (path, body = {}) => req(path, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
})

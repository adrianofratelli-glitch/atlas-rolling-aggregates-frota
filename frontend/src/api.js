const FORA = 'Backend fora do ar em 127.0.0.1:8410 — rode `make api`.'

async function req(url, opts) {
  let r
  try {
    r = await fetch(url, opts)
  } catch {
    throw Object.assign(new Error(FORA), { foraDoAr: true })
  }
  const corpo = await r.json().catch(() => null)
  // em dev o proxy do Vite responde 5xx sem JSON quando a API não está de pé
  if (!corpo && r.status >= 500) throw Object.assign(new Error(FORA), { foraDoAr: true })
  if (!r.ok) {
    const msg = corpo?.erro ? `${corpo.erro}${corpo.acao ? ` — ${corpo.acao}` : ''}` : `HTTP ${r.status}`
    throw Object.assign(new Error(msg), { status: r.status })
  }
  return corpo ?? {}
}
const qs = (p) => new URLSearchParams(Object.entries(p).filter(([, v]) => v !== '' && v != null)).toString()
export const get = (path, params = {}) => req(`${path}?${qs(params)}`)
export const post = (path, body = {}) => req(path, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
})

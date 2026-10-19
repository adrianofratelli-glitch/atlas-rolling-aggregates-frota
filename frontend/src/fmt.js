// Formatação em pt-BR e no fuso da POV (a API manda instantes em UTC).
const TZ = 'America/Sao_Paulo'

export const num = (v, casas = 1) => (v == null ? '—'
  : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas }))
export const int = (v) => (v == null ? '—' : Number(v).toLocaleString('pt-BR'))

const parte = (iso, opts) => new Intl.DateTimeFormat('pt-BR', { timeZone: TZ, ...opts }).format(new Date(iso))
export const dataLocal = (iso) => (iso ? parte(iso, { day: '2-digit', month: '2-digit', year: 'numeric' }) : '—')
export const ddmm = (iso) => (iso ? parte(iso, { day: '2-digit', month: '2-digit' }) : '—')
export const horaLocal = (iso) => (iso ? parte(iso, { hour: '2-digit', minute: '2-digit' }) : '—')
export const diaSemana = (iso) => (iso ? parte(iso, { weekday: 'short' }).replace('.', '') : '—')
export const dataHora = (iso) => (iso ? `${ddmm(iso)} ${horaLocal(iso)}` : '—')

// "2026-10-19" (data local, sem fuso) → "19/10/2026"
export const dataIso = (s) => (s ? s.split('-').reverse().join('/') : '—')
// soma dias a uma data local "AAAA-MM-DD" sem passar por fuso
export const somaDias = (s, n) => {
  const d = new Date(`${s}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

export const DIAS_CURTOS = { 1: 'seg', 2: 'ter', 3: 'qua', 4: 'qui', 5: 'sex', 6: 'sáb', 7: 'dom' }
export const h2 = (h) => `${String(h).padStart(2, '0')}h`

export function descreveDias(dias) {
  if (!dias?.length) return '—'
  if (dias.length === 7) return 'todos os dias'
  return dias.map((d) => DIAS_CURTOS[d]).join(', ')
}

// horas [12..17] → "12h → 18h"; faixa que cruza a meia-noite [18..23,0..5] → "18h → 06h"
export function descreveHoras(horas) {
  if (!horas?.length) return '—'
  if (horas.length === 24) return 'dia inteiro'
  let ini = horas[0]
  for (let i = 1; i < horas.length; i++) if (horas[i] !== (horas[i - 1] + 1) % 24) ini = horas[i]
  const fim = (horas[horas.length - 1] + 1) % 24
  return `${h2(ini)} → ${h2(fim === 0 ? 24 : fim)}`
}

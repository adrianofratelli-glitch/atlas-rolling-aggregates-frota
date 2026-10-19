import { useEffect, useRef, useState } from 'react'
import { post } from '../api.js'
import { DIAS_CURTOS, h2 } from '../fmt.js'

const ROTULO_ATALHO = { manha: 'Manhã', tarde: 'Tarde', noite: 'Noite' }

export const chaveTrecho = (t) => `${t.origem}|${t.destino}`

export function filtroInicial(opcoes, { esparso = false } = {}) {
  const t = opcoes.trechos.find((x) => x.esparso === esparso) || opcoes.trechos[0]
  const tarde = opcoes.atalhos.tarde || { inicio: 12, fim: 18 }
  return { origem: t?.origem || '', destino: t?.destino || '', tipoVeiculo: 'CARRETA',
    dias: [5], horaInicio: tarde.inicio, horaFim: tarde.fim }
}

// Consulta automática com debounce; só a última resposta pedida é mostrada.
export function useConsultaAuto(corpo, ativo = true, espera = 300) {
  const [estado, setEstado] = useState({ resposta: null, erro: '', carregando: false })
  const seq = useRef(0)
  const json = JSON.stringify(corpo)
  useEffect(() => {
    if (!ativo || !corpo?.origem) return undefined
    const n = ++seq.current
    setEstado((e) => ({ ...e, carregando: true }))
    const t = setTimeout(() => {
      post('/api/cenario', corpo)
        .then((r) => { if (n === seq.current) setEstado({ resposta: r, erro: '', carregando: false }) })
        .catch((e) => { if (n === seq.current) setEstado((x) => ({ ...x, erro: e.message, carregando: false })) })
    }, espera)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [json, ativo])
  return estado
}

export default function FiltroCenario({ valor, onChange, opcoes, children }) {
  const set = (campos) => onChange({ ...valor, ...campos })
  const alternarDia = (d) => {
    const tem = valor.dias.includes(d)
    if (tem && valor.dias.length === 1) return // ao menos um dia
    set({ dias: tem ? valor.dias.filter((x) => x !== d) : [...valor.dias, d].sort() })
  }
  return (
    <form className="filtro" onSubmit={(e) => e.preventDefault()} aria-label="Cenário">
      <div className="filtro-linha">
        <label className="campo largo">Trecho
          <select value={`${valor.origem}|${valor.destino}`}
            onChange={(e) => { const [origem, destino] = e.target.value.split('|'); set({ origem, destino }) }}>
            {opcoes.trechos.map((t) => (
              <option key={chaveTrecho(t)} value={chaveTrecho(t)}>
                {t.nomeOrigem} → {t.nomeDestino}{t.esparso ? ' · poucos dados' : ''}
              </option>
            ))}
          </select>
        </label>
        <label className="campo">Veículo
          <select value={valor.tipoVeiculo} onChange={(e) => set({ tipoVeiculo: e.target.value })}>
            {opcoes.tipos.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
      </div>
      <fieldset className="sem-borda">
        <legend>Dias da semana</legend>
        <div className="dias" role="group" aria-label="Dias da semana">
          {[1, 2, 3, 4, 5, 6, 7].map((d) => (
            <button type="button" key={d} className="chip-btn" aria-pressed={valor.dias.includes(d)}
              title={opcoes.dias?.[d]} onClick={() => alternarDia(d)}>{DIAS_CURTOS[d]}</button>
          ))}
        </div>
      </fieldset>
      <div className="filtro-linha">
        <label className="campo curto">Das
          <select value={valor.horaInicio} onChange={(e) => set({ horaInicio: Number(e.target.value) })}>
            {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{h2(h)}</option>)}
          </select>
        </label>
        <label className="campo curto">Até
          <select value={valor.horaFim} onChange={(e) => set({ horaFim: Number(e.target.value) })}>
            {Array.from({ length: 24 }, (_, i) => i + 1).map((h) => <option key={h} value={h}>{h2(h)}</option>)}
          </select>
        </label>
        <div className="atalhos" role="group" aria-label="Atalhos de horário">
          {Object.entries(opcoes.atalhos).map(([k, a]) => (
            <button type="button" key={k} className="chip-btn"
              aria-pressed={valor.horaInicio === a.inicio && valor.horaFim === a.fim}
              onClick={() => set({ horaInicio: a.inicio, horaFim: a.fim })}>
              {ROTULO_ATALHO[k] || k} <small>{h2(a.inicio)}–{h2(a.fim)}</small>
            </button>
          ))}
        </div>
      </div>
      {children}
    </form>
  )
}

import { useEffect, useRef, useState } from 'react'
import { post } from '../api.js'
import { DIAS_CURTOS, h2 } from '../fmt.js'

const ROTULO_ATALHO = { manha: 'Manhã', tarde: 'Tarde', noite: 'Noite' }

export function filtroInicial(opcoes) {
  const t = opcoes.trechos.find((x) => !x.esparso) || opcoes.trechos[0]
  const tarde = opcoes.atalhos.tarde || { inicio: 12, fim: 18 }
  return { origem: t?.origem || '', destino: t?.destino || '', tipoVeiculo: 'CARRETA', veiculoId: '',
    dias: [5], horaInicio: tarde.inicio, horaFim: tarde.fim }
}

// O filtro guardado no App ainda vale com as opções atuais (depois de um reset, por exemplo)?
export function filtroValido(f, opcoes) {
  if (!f || !opcoes.trechos.some((t) => t.origem === f.origem && t.destino === f.destino)) return false
  return !f.veiculoId || (opcoes.veiculos?.[f.tipoVeiculo] || []).includes(f.veiculoId)
}

// tipos que fazem o trecho (viagem longa só com os pesados); o escolhido muda se deixar de valer
const tiposDo = (opcoes, origem, destino) =>
  opcoes.trechos.find((t) => t.origem === origem && t.destino === destino)?.tipos || opcoes.tipos
const comTipoValido = (opcoes, v) => {
  const tipos = tiposDo(opcoes, v.origem, v.destino)
  return tipos.includes(v.tipoVeiculo) ? v : { ...v, tipoVeiculo: tipos[tipos.length - 2] || tipos[0], veiculoId: '' }
}

// ao trocar a origem, o destino vai para o primeiro válido (com dados regulares, se houver)
const primeiroDestino = (trechos, origem) => {
  const ds = trechos.filter((t) => t.origem === origem)
  return (ds.find((t) => !t.esparso) || ds[0])?.destino || ''
}
// origens sem repetir, na ordem dos trechos (a API já ordena por origem e destino)
const origens = (trechos) => [...new Map(trechos.map((t) => [t.origem, t.nomeOrigem])).entries()]

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
  const set = (campos) => onChange(comTipoValido(opcoes, { ...valor, ...campos }))
  const tipos = tiposDo(opcoes, valor.origem, valor.destino)
  const destinos = opcoes.trechos.filter((t) => t.origem === valor.origem)
  const alternarDia = (d) => {
    const tem = valor.dias.includes(d)
    if (tem && valor.dias.length === 1) return // ao menos um dia
    set({ dias: tem ? valor.dias.filter((x) => x !== d) : [...valor.dias, d].sort() })
  }
  return (
    <form className="filtro" onSubmit={(e) => e.preventDefault()} aria-label="Cenário">
      <div className="filtro-linha">
        <label className="campo">Origem
          <select name="origem" value={valor.origem}
            onChange={(e) => set({ origem: e.target.value, destino: primeiroDestino(opcoes.trechos, e.target.value) })}>
            {origens(opcoes.trechos).map(([id, nome]) => <option key={id} value={id}>{nome}</option>)}
          </select>
        </label>
        <label className="campo">Destino
          <select name="destino" value={valor.destino} onChange={(e) => set({ destino: e.target.value })}>
            {destinos.map((t) => (
              <option key={t.destino} value={t.destino}>{t.nomeDestino}{t.esparso ? ' · poucos dados' : ''}</option>
            ))}
          </select>
        </label>
        <label className="campo">Tipo de veículo
          <select name="tipoVeiculo" value={valor.tipoVeiculo} onChange={(e) => set({ tipoVeiculo: e.target.value, veiculoId: '' })}>
            {tipos.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label className="campo">Veículo
          <select name="veiculoId" value={valor.veiculoId || ''} onChange={(e) => set({ veiculoId: e.target.value })}>
            <option value="">todos os veículos do tipo</option>
            {(opcoes.veiculos?.[valor.tipoVeiculo] || []).map((v) => <option key={v} value={v}>{v}</option>)}
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

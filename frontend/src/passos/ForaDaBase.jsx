import { useState } from 'react'
import { post } from '../api.js'
import { somaDias } from '../fmt.js'
import FiltroCenario from '../comp/FiltroCenario.jsx'
import GavetaQuery from '../comp/GavetaQuery.jsx'
import Resultado from '../comp/Resultado.jsx'

// Período fora da janela padrão: agrega a raw na hora, só quando o apresentador pede.
export default function ForaDaBase({ opcoes, filtro, setFiltro, estado }) {
  const hoje = estado.dataRef
  const [p, setP] = useState({ tipo: 'datas', de: somaDias(hoje, -28), ate: somaDias(hoje, -1), dias: 30,
    persistir: false, ttlDias: 7 })
  const [estadoCalc, setEstadoCalc] = useState({ resposta: null, erro: '', carregando: false, corpo: '' })
  const set = (c) => setP((x) => ({ ...x, ...c }))

  const periodo = p.tipo === 'datas' ? { tipo: 'datas', de: p.de, ate: p.ate } : { tipo: 'ultimos', dias: Number(p.dias) }
  const corpo = { ...filtro, periodo, persistir: p.persistir,
    ...(p.persistir && p.tipo === 'datas' ? { ttlDias: Number(p.ttlDias) } : {}) }
  const chave = JSON.stringify(corpo)

  const calcular = async () => {
    setEstadoCalc((e) => ({ ...e, carregando: true, erro: '' }))
    try {
      const r = await post('/api/cenario', corpo)
      setEstadoCalc({ resposta: r, erro: '', carregando: false, corpo: chave })
    } catch (e) {
      setEstadoCalc((x) => ({ ...x, erro: e.message, carregando: false }))
    }
  }
  const { resposta, erro, carregando } = estadoCalc

  return (
    <>
      <FiltroCenario valor={filtro} onChange={setFiltro} opcoes={opcoes}>
        <fieldset className="sem-borda">
          <legend>Período</legend>
          <div className="filtro-linha">
          <div className="seg" role="group" aria-label="Tipo de período">
            <button type="button" aria-pressed={p.tipo === 'datas'} onClick={() => set({ tipo: 'datas' })}>Datas específicas</button>
            <button type="button" aria-pressed={p.tipo === 'ultimos'} onClick={() => set({ tipo: 'ultimos' })}>Últimos N dias</button>
          </div>
          {p.tipo === 'datas' ? (
            <>
              <label className="campo curto">De<input type="date" value={p.de} max={p.ate} onChange={(e) => set({ de: e.target.value })} /></label>
              <label className="campo curto">Até<input type="date" value={p.ate} min={p.de} max={hoje} onChange={(e) => set({ ate: e.target.value })} /></label>
            </>
          ) : (
            <label className="campo curto">Dias<input type="number" min="1" max="200" value={p.dias} onChange={(e) => set({ dias: e.target.value })} /></label>
          )}
          </div>
        </fieldset>
        <div className="filtro-linha persistir">
          <label className="check"><input type="checkbox" checked={p.persistir} onChange={(e) => set({ persistir: e.target.checked })} /> persistir este resultado</label>
          {p.persistir && (p.tipo === 'datas' ? (
            <label className="campo curto inline">validade (dias)
              <input type="number" min="1" max="30" value={p.ttlDias} onChange={(e) => set({ ttlDias: e.target.value })} />
            </label>
          ) : <span className="nota">expira no próximo job</span>)}
        </div>
        <div className="acao">
          <button type="button" className="primario" onClick={calcular} disabled={carregando} aria-busy={carregando}>
            {carregando ? 'Calculando na raw…' : 'Calcular'}
          </button>
        </div>
      </FiltroCenario>
      {erro && <p className="aviso erro" role="alert">{erro}</p>}
      {(resposta || carregando) && (
        <Resultado resposta={resposta} carregando={carregando}
          desatualizado={!!resposta && estadoCalc.corpo !== chave} />
      )}
      {resposta && <GavetaQuery query={resposta.query} />}
    </>
  )
}

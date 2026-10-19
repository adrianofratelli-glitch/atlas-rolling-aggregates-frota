import { useState } from 'react'
import { post } from '../api.js'
import { somaDias } from '../fmt.js'
import FiltroCenario, { useConsultaAuto } from '../comp/FiltroCenario.jsx'
import GavetaQuery from '../comp/GavetaQuery.jsx'
import Resultado from '../comp/Resultado.jsx'
import MapaFluxo from '../comp/MapaFluxo.jsx'

const RAMO_BASE = ['base', 'eta', 'e-base-eta']
const RAMO_RAW = ['raw', 'salvas', 'eta', 'e-raw-salvas', 'e-salvas-eta']
// Ramo aceso conforme `origem` da resposta: base pronta; lido do salvo (só salvas → ETA);
// calculado na raw e gravado (ramo inteiro); calculado sem gravar (raw → ETA, e o caminho do
// $merge e consultas_salvas parciais: nada foi escrito); sem dado bruto no período (nada rodou:
// só a raw parcial). Antes da primeira resposta, os dois ramos em opacidade média.
function ramos(r) {
  if (!r) return { parcial: [...RAMO_BASE, ...RAMO_RAW] }
  if (r.origem === 'base' || r.selo === 'job_diario') return { ativo: RAMO_BASE }
  if (r.origem === 'salvo') return { ativo: ['salvas', 'eta', 'e-salvas-eta'] }
  if (!r.resultado) return { parcial: ['raw'] }
  if (r.expiraEm) return { ativo: RAMO_RAW }
  return { ativo: ['raw', 'eta'], parcial: ['salvas', 'e-raw-salvas', 'e-salvas-eta'] }
}

// O detalhe da API já descreve o nível usado ("poucas amostras: ampliado para …",
// "sem histórico suficiente…"); aqui entra só a etiqueta, para não repetir o texto.
function Ampliacao({ nivel }) {
  if (!nivel || nivel === 'pedido') return null
  return <p className="ampliacao"><span className="tag alerta">regra a validar com o cliente</span></p>
}

// Uma consulta só: a API decide se soma a base pronta ou calcula na raw (e guarda).
// Janela padrão sem veículo responde sozinha; qualquer outro caso espera o botão Calcular.
export default function Consultar({ opcoes, filtro, setFiltro, estado, ocupado }) {
  const hoje = estado.dataRef
  const [p, setP] = useState({ tipo: 'padrao', de: somaDias(hoje, -28), ate: somaDias(hoje, -1), dias: 30,
    persistir: true, ttlDias: 7 })
  const [calc, setCalc] = useState({ resposta: null, erro: '', carregando: false, corpo: '' })
  const set = (c) => setP((x) => ({ ...x, ...c }))

  const { veiculoId, ...rota } = filtro
  const auto = p.tipo === 'padrao' && !veiculoId
  const periodo = p.tipo === 'padrao' ? { tipo: 'padrao' }
    : p.tipo === 'datas' ? { tipo: 'datas', de: p.de, ate: p.ate } : { tipo: 'ultimos', dias: Number(p.dias) }
  const relativo = p.tipo !== 'datas'
  const corpo = { ...rota, ...(veiculoId ? { veiculoId } : {}), periodo, persistir: p.persistir,
    ...(p.persistir && !relativo ? { ttlDias: Number(p.ttlDias) } : {}) }
  const chave = JSON.stringify(corpo)
  const autoEstado = useConsultaAuto({ ...rota, periodo }, auto && !ocupado)

  const calcular = async () => {
    setCalc((e) => ({ ...e, carregando: true, erro: '' }))
    try {
      const r = await post('/api/cenario', corpo)
      setCalc({ resposta: r, erro: '', carregando: false, corpo: chave })
    } catch (e) {
      setCalc((x) => ({ ...x, erro: e.message, carregando: false }))
    }
  }
  const { resposta, erro, carregando } = auto ? autoEstado : calc

  return (
    <>
      <MapaFluxo {...ramos(resposta)} horario={estado.trigger.horarioLocal} />
      <FiltroCenario valor={filtro} onChange={setFiltro} opcoes={opcoes}>
        <fieldset className="sem-borda">
          <legend>Período</legend>
          <div className="filtro-linha">
            <div className="seg" role="group" aria-label="Tipo de período">
              <button type="button" aria-pressed={p.tipo === 'padrao'} onClick={() => set({ tipo: 'padrao' })}>Janela padrão (últimos {estado.janela.dias} dias)</button>
              <button type="button" aria-pressed={p.tipo === 'datas'} onClick={() => set({ tipo: 'datas' })}>Datas específicas</button>
              <button type="button" aria-pressed={p.tipo === 'ultimos'} onClick={() => set({ tipo: 'ultimos' })}>Últimos N dias</button>
            </div>
            {p.tipo === 'datas' && (
              <>
                <label className="campo curto">De<input type="date" value={p.de} max={p.ate} onChange={(e) => set({ de: e.target.value })} /></label>
                <label className="campo curto">Até<input type="date" value={p.ate} min={p.de} max={hoje} onChange={(e) => set({ ate: e.target.value })} /></label>
              </>
            )}
            {p.tipo === 'ultimos' && (
              <label className="campo curto">Dias<input type="number" min="1" max="200" value={p.dias} onChange={(e) => set({ dias: e.target.value })} /></label>
            )}
          </div>
        </fieldset>
        {!auto && (
          <>
            <div className="filtro-linha persistir">
              <label className="check"><input type="checkbox" checked={p.persistir} onChange={(e) => set({ persistir: e.target.checked })} /> guardar o resultado</label>
              {p.persistir && (relativo ? <span className="nota">vale até o próximo job</span> : (
                <label className="campo curto inline">validade (dias)
                  <input type="number" min="1" max="30" value={p.ttlDias} onChange={(e) => set({ ttlDias: e.target.value })} />
                </label>
              ))}
            </div>
            <div className="acao">
              <button type="button" className="primario" onClick={calcular} disabled={carregando} aria-busy={carregando}>
                {carregando ? 'Calculando…' : 'Calcular'}
              </button>
            </div>
          </>
        )}
      </FiltroCenario>
      <p className="frase">Se a média já estiver pré-calculada, vem da base pronta; senão é calculada agora (e guardada, se marcado).</p>
      {erro && <p className="aviso erro" role="alert">{erro}</p>}
      <Resultado resposta={resposta} carregando={carregando}
        desatualizado={!auto && !!resposta && calc.corpo !== chave} />
      {resposta && <Ampliacao nivel={resposta.nivel} />}
      {resposta && <GavetaQuery query={resposta.query} geradoPor={resposta.geradoPor} />}
    </>
  )
}

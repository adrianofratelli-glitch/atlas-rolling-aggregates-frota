import { useState } from 'react'
import FiltroCenario, { filtroInicial, useConsultaAuto } from '../comp/FiltroCenario.jsx'
import GavetaQuery from '../comp/GavetaQuery.jsx'
import Resultado from '../comp/Resultado.jsx'

const NIVEIS = [
  ['pedido', 'Dias e horas pedidos'],
  ['todos_os_dias', 'Todos os dias da semana, mesmas horas'],
  ['dia_inteiro', 'Dia inteiro, nos dias pedidos'],
  ['sem_historico', 'Sem histórico suficiente'],
]

// Trecho esparso: mostra em que degrau da ampliação a média foi encontrada.
export default function PoucasAmostras({ opcoes, ocupado, minAmostras = 5 }) {
  const [filtro, setFiltro] = useState(() => filtroInicial(opcoes, { esparso: true }))
  const { resposta, erro, carregando } = useConsultaAuto({ ...filtro, periodo: { tipo: 'padrao' } }, !ocupado)
  const atual = resposta?.nivel
  return (
    <>
      <FiltroCenario valor={filtro} onChange={setFiltro} opcoes={opcoes} />
      {erro && <p className="aviso erro" role="alert">{erro}</p>}
      <div className="duas estreita">
        <Resultado resposta={resposta} carregando={carregando} />
        <section className="cartao">
          <h3>Se faltam amostras <span className="tag alerta">regra a validar com o cliente</span></h3>
          <p className="nota">Menos de {minAmostras} amostras: amplia um degrau por vez.</p>
          <ol className="niveis">
            {NIVEIS.map(([k, rotulo]) => (
              <li key={k} className={atual === k ? 'ativo' : ''} aria-current={atual === k ? 'step' : undefined}>
                <span>{rotulo}</span>{atual === k && <b>usado</b>}
              </li>
            ))}
          </ol>
        </section>
      </div>
      {resposta && <GavetaQuery query={resposta.query} geradoPor={resposta.geradoPor} />}
    </>
  )
}

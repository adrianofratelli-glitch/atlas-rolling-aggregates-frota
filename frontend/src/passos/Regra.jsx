import { dataIso, dataLocal, somaDias } from '../fmt.js'
import MapaFluxo from '../comp/MapaFluxo.jsx'

const ATIVO = ['raw', 'job', 'e-raw-job']

// A regra em linguagem simples, com as datas concretas da janela de hoje.
export default function Regra({ estado }) {
  const j = estado.janela
  const ultimoDia = somaDias(estado.dataRef, -1)
  return (
    <>
      <MapaFluxo ativo={ATIVO} horario={estado.trigger.horarioLocal} />
      <ol className="regra">
        <li><b>Janela de {j.dias} dias</b><span>do dia {dataLocal(j.inicio)} até o dia {dataIso(ultimoDia)}. Hoje ({dataIso(estado.dataRef)}) fica de fora: o dia ainda não terminou.</span></li>
        <li><b>Chave da média</b><span>trecho × tipo de veículo × dia da semana × hora</span></li>
        <li><b>Horário de São Paulo</b><span>dia da semana de 1 (segunda) a 7 (domingo) e hora de 0 a 23, no fuso local.</span></li>
        <li><b>Recalcula todo dia</b><span>o job das {estado.trigger.horarioLocal} empurra a janela um dia para a frente.</span></li>
      </ol>
      <div className="janela" aria-label="Janela de hoje">
        <div><span className="pov-eyebrow">início (entra)</span><strong className="num">{dataLocal(j.inicio)} 00:00</strong></div>
        <div className="seta" aria-hidden="true">→</div>
        <div><span className="pov-eyebrow">fim (fica de fora)</span><strong className="num">{dataLocal(j.fim)} 00:00</strong></div>
      </div>
      <p className="nota">Em query: <code>observadoEm ≥ início</code> e <code>observadoEm &lt; fim</code>.</p>
    </>
  )
}

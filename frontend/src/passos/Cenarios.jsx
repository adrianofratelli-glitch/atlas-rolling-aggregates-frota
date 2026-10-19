import FiltroCenario, { useConsultaAuto } from '../comp/FiltroCenario.jsx'
import GavetaQuery from '../comp/GavetaQuery.jsx'
import Resultado from '../comp/Resultado.jsx'

export default function Cenarios({ opcoes, filtro, setFiltro, estado, ocupado }) {
  const { resposta, erro, carregando } = useConsultaAuto({ ...filtro, periodo: { tipo: 'padrao' } }, !ocupado)
  return (
    <>
      <FiltroCenario valor={filtro} onChange={setFiltro} opcoes={opcoes}>
        <p className="periodo-fixo"><span className="pov-eyebrow">período</span> janela padrão · últimos {estado.janela.dias} dias</p>
      </FiltroCenario>
      {erro && <p className="aviso erro" role="alert">{erro}</p>}
      <Resultado resposta={resposta} carregando={carregando} />
      <p className="frase">É isto que a aplicação lê quando o serviço de ETA online cai.</p>
      {resposta && <GavetaQuery query={resposta.query} geradoPor={resposta.geradoPor} />}
    </>
  )
}

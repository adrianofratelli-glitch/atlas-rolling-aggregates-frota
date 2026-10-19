import { dataHora, descreveDias, descreveHoras, int, num } from '../fmt.js'
import Selo from './Selo.jsx'

// Resposta de /api/cenario: número grande, selo de origem e os contadores que provam o custo.
// O tempo medido é quase todo ida e volta de rede; a prova de custo é `docs lidos`.
export default function Resultado({ resposta, carregando, desatualizado }) {
  if (!resposta) {
    return <div className="resultado vazio" aria-live="polite">{carregando ? 'Consultando…' : 'Sem resultado ainda.'}</div>
  }
  const r = resposta.resultado
  const semAmostra = !r || !r.n
  return (
    <div className={`resultado${carregando || desatualizado ? ' atualizando' : ''}`}
      aria-busy={carregando ? 'true' : 'false'} aria-live="polite">
      <Selo selo={resposta.selo} detalhe={resposta.detalhe} />
      {semAmostra ? (
        <p className="sem-amostra">{resposta.aviso || 'Nenhuma amostra para esse cenário.'}</p>
      ) : (
        <>
          <p className="numero">
            <strong className="pov-stat">{num(r.mediaMin)}</strong><span className="unid">min</span>
            <span className="desvio">± {num(r.desvioMin)} min</span>
            <span className="km">{num(r.mediaKm)} km</span>
          </p>
          <dl className="contas">
            <div><dt>amostras</dt><dd>{int(r.n)}</dd></div>
            <div><dt>dias somados</dt><dd>{descreveDias(r.diasSomados)}</dd></div>
            <div><dt>horas</dt><dd>{descreveHoras(r.horas)}</dd></div>
            {r.docsExaminados != null ? (
              // com veículo, o índice percorre o trecho × tipo inteiro: esse é o custo
              <div className="custo"><dt>docs lidos</dt><dd>{int(r.docsExaminados)}</dd>
                <dd className="sub">{int(r.docsLidos)} do veículo · o índice percorre o trecho × tipo inteiro</dd></div>
            ) : <div className="custo"><dt>docs lidos</dt><dd>{int(r.docsLidos)}</dd></div>}
            <div title="Inclui a rede até o banco: no Atlas é quase todo ida e volta. O custo está em docs lidos.">
              <dt>ida e volta ao banco</dt><dd>{num(r.ms, 1)} ms</dd></div>
          </dl>
          {resposta.aviso && <p className="aviso">{resposta.aviso}</p>}
        </>
      )}
      {resposta.expiraEm && <p className="nota">Salvo em <code>consultas_salvas</code> até {dataHora(resposta.expiraEm)}.</p>}
      {carregando && <p className="nota">Atualizando…</p>}
      {desatualizado && !carregando && <p className="nota">O filtro mudou: clique em Calcular.</p>}
    </div>
  )
}

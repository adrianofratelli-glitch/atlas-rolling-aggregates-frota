import { useState } from 'react'
import { post } from '../api.js'
import { dataHora, int, num } from '../fmt.js'
import GavetaQuery from '../comp/GavetaQuery.jsx'

const nomeEstagio = (e) => Object.keys(e)[0]

export default function GerarBase({ estado, onMudou }) {
  const [run, setRun] = useState(null)
  const [rodando, setRodando] = useState(false)
  const [erro, setErro] = useState('')
  const ultimo = estado.ultimoJob

  const rodar = async () => {
    setRodando(true); setErro('')
    try {
      setRun(await post('/api/job'))
      onMudou()
    } catch (e) {
      setErro(e.message)
    } finally {
      setRodando(false)
    }
  }

  return (
    <>
      <div className="acao">
        <button type="button" className="primario" onClick={rodar} disabled={rodando} aria-busy={rodando}>
          {rodando ? 'Rodando o job… (alguns segundos)' : 'Rodar job agora'}
        </button>
        {!run && ultimo && (
          <span className="nota">Última execução: {dataHora(ultimo.iniciadoEm)} · {int(ultimo.gravados)} médias gravadas</span>
        )}
      </div>
      {erro && <p className="aviso erro" role="alert">{erro}</p>}
      {run && (
        <>
          <dl className="contadores" aria-label="Resultado do job">
            <div><dt>observações lidas</dt><dd className="pov-stat">{int(run.lidos)}</dd></div>
            <div><dt>médias gravadas</dt><dd className="pov-stat">{int(run.gravados)}</dd></div>
            <div><dt>removidas</dt><dd className="pov-stat">{int(run.removidos)}</dd></div>
            <div><dt>tempo</dt><dd className="pov-stat">{num(run.ms / 1000, 1)} s</dd></div>
          </dl>
          <ol className="pipeline" aria-label="Pipeline do job, estágio a estágio">
            {run.pipeline.map((e, i) => {
              const op = nomeEstagio(e.estagio)
              const merge = op === '$merge'
              return (
                <li key={i} className={merge ? 'destaque' : ''}>
                  <code className="op">{op}</code>
                  <span>{e.comentario}</span>
                  {merge && <strong className="mv">É a “materialized view”: a base fica pronta para leitura.</strong>}
                </li>
              )
            })}
          </ol>
          <GavetaQuery query={run.query} />
        </>
      )}
    </>
  )
}

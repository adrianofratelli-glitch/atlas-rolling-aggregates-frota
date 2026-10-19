import { useState } from 'react'
import { get, post } from '../api.js'
import { dataHora, int, num } from '../fmt.js'
import GavetaQuery from '../comp/GavetaQuery.jsx'
import MapaFluxo from '../comp/MapaFluxo.jsx'

// O script que o cliente colocaria no Atlas: a Function e a configuração do Scheduled Trigger.
function ScriptTrigger() {
  const [d, setD] = useState(null)
  const [erro, setErro] = useState('')
  const [copiado, setCopiado] = useState('')
  const abrir = (e) => {
    if (e.currentTarget.open && !d) get('/api/trigger-script').then(setD).catch((x) => setErro(x.message))
  }
  const copiar = async (chave, texto) => {
    try { await navigator.clipboard.writeText(texto); setCopiado(chave) } catch { setCopiado('') }
    setTimeout(() => setCopiado(''), 1600)
  }
  return (
    <details className="gaveta" onToggle={abrir}>
      <summary>Ver o script do Atlas Trigger</summary>
      <div className="gaveta-corpo">
        <p className="nota">É isto que o cliente rodaria no Atlas: o botão acima executa o mesmo pipeline,
          e o <b>Scheduled Trigger</b> o dispara todo dia{d ? ` às ${d.horarioLocal} (horário de São Paulo)` : ''}.</p>
        {erro && <p className="aviso erro" role="alert">{erro}</p>}
        {!d && !erro && <p className="nota">Carregando…</p>}
        {d && [['trigger', 'Agendamento (Scheduled Trigger)'], ['funcao', 'Function que roda o job']].map(([k, titulo]) => (
          <div className="codigo" key={k}>
            <div className="codigo-cab">
              <span className="nota">{titulo} · <code>{d[k].arquivo}</code></span>
              <button type="button" className="copiar" onClick={() => copiar(k, d[k].codigo)} aria-live="polite">{copiado === k ? 'copiado ✓' : 'copiar'}</button>
            </div>
            <pre tabIndex={0} aria-label={titulo}><code>{d[k].codigo}</code></pre>
          </div>
        ))}
      </div>
    </details>
  )
}

const nomeEstagio = (e) => Object.keys(e)[0]
const ATIVO = ['raw', 'job', 'base', 'e-raw-job', 'e-job-base']

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
      <MapaFluxo ativo={ATIVO} horario={estado.trigger.horarioLocal} animar={rodando}
        numeros={run && !rodando ? { raw: run.lidos, base: run.gravados } : null} />
      <div className="acao">
        <button type="button" className="primario" onClick={rodar} disabled={rodando} aria-busy={rodando}>
          {rodando ? 'Rodando o job… (alguns segundos)' : 'Rodar job agora'}
        </button>
        {!run && ultimo && (
          <span className="nota">Última execução: {dataHora(ultimo.iniciadoEm)} · {int(ultimo.gravados)} médias gravadas</span>
        )}
        {!run && estado.ultimoErro && (
          <span className="nota">Tentativa de {dataHora(estado.ultimoErro.iniciadoEm)} falhou; a base continua a da última execução.</span>
        )}
      </div>
      {erro && <p className="aviso erro" role="alert">{erro}</p>}
      <ScriptTrigger />
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
              // no $merge, só a frase curta e o rótulo; o comentário completo fica na gaveta
              return (
                <li key={i} className={merge ? 'destaque' : ''}>
                  <code className="op">{op}</code>
                  {merge
                    ? <span>Grava o resultado numa collection persistente. <strong className="mv">materialized view</strong></span>
                    : <span>{e.comentario}</span>}
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

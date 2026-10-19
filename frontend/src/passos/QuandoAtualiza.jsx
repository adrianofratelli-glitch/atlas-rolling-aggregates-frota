import { useEffect, useState } from 'react'
import { get } from '../api.js'
import { dataHora, dataIso, int, num } from '../fmt.js'

const ORIGEM = { trigger: 'trigger', botao: 'botão', cli: 'make job', reset: 'reset' }

export default function QuandoAtualiza({ estado, ocupado }) {
  const [runs, setRuns] = useState(null)
  const [prev, setPrev] = useState(null)
  const [erro, setErro] = useState('')
  useEffect(() => {
    if (ocupado) return
    Promise.all([get('/api/job_runs', { limite: 5 }), get('/api/proximo-job')])
      .then(([r, p]) => { setRuns(r); setPrev(p); setErro('') })
      .catch((e) => setErro(e.message))
  }, [ocupado])
  const t = estado.trigger
  return (
    <>
      <div className="duas">
        <section className="cartao">
          <h3>Agendamento</h3>
          {t.implantado ? (
            <p className="agenda"><strong className="pov-stat">{t.horarioLocal}</strong>
              <span>todo dia, horário de São Paulo<br /><small>Atlas Scheduled Trigger · cron UTC <code>{t.cron}</code></small></span></p>
          ) : (
            <>
              <p className="agenda"><strong className="pov-stat">{t.horarioLocal}</strong>
                <span>todo dia, horário de São Paulo<br /><small>no Atlas: Scheduled Trigger · cron UTC <code>{t.cron}</code></small></span></p>
              <p className="selo-linha"><span className="selo pendente"><span aria-hidden="true">○</span>trigger não implantado neste alvo</span></p>
              <p className="nota">Aqui, rode <code>make job</code> ou o botão do passo 3.</p>
            </>
          )}
        </section>
        <section className="cartao">
          <h3>Próximo job {prev && <small>{dataHora(prev.quando)}</small>}</h3>
          {prev ? (
            <ul className="previa">
              <li className="entra"><b>entra</b><span>{dataIso(prev.entra.dia)}</span><span className="num">{int(prev.entra.observacoes)} observações</span></li>
              <li className="sai"><b>sai</b><span>{dataIso(prev.sai.dia)}</span><span className="num">{int(prev.sai.observacoes)} observações</span></li>
              <li className="chaves"><b>chaves que somem<small>sem nenhuma observação na nova janela</small></b><span className="num">{int(prev.chavesQueSomem)}</span></li>
            </ul>
          ) : !erro && <p className="nota">Carregando a prévia…</p>}
        </section>
      </div>
      <p className="frase"><code>$merge</code> materializa; quem atualiza é o job, não o banco.</p>
      {erro && <p className="aviso erro" role="alert">{erro}</p>}
      {runs && (
        <section className="cartao">
          <h3>Últimas execuções</h3>
          {runs.length === 0 ? <p className="nota">Nenhuma execução ainda.</p> : (
            <div className="rolagem" tabIndex={0} aria-label="Últimas execuções do job">
              <table>
                <thead><tr><th>quando</th><th>origem</th><th>dia de referência</th><th className="dir">lidas</th><th className="dir">gravadas</th><th className="dir">removidas</th><th className="dir">tempo</th></tr></thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r._id}>
                      <td>{dataHora(r.iniciadoEm)}</td>
                      <td>{ORIGEM[r.origem] || r.origem}{r.status !== 'ok' && <span className="erro"> · ⚠ erro</span>}</td>
                      <td>{dataIso(r.dataRef)}</td>
                      <td className="dir">{int(r.lidos)}</td><td className="dir">{int(r.gravados)}</td>
                      <td className="dir">{int(r.removidos)}</td><td className="dir">{num((r.ms || 0) / 1000, 1)} s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </>
  )
}

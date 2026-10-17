import { Component, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { get, post } from './api.js'

const DOW = { 1: 'dom', 2: 'seg', 3: 'ter', 4: 'qua', 5: 'qui', 6: 'sex', 7: 'sáb' }
const fmt = (v, d = 1) => (v == null ? '—' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: d, minimumFractionDigits: d }))
const int = (v) => (v == null ? '—' : Number(v).toLocaleString('pt-BR'))

const ABAS = [
  ['eta', 'Consulta ETA'],
  ['raw', 'Raw vs Materializado'],
  ['modos', 'Simples × Incremental'],
  ['job', 'Job e janela'],
  ['config', 'Config'],
]

// ------------------------------------------------------------------ peças comuns

function Badges({ itens }) {
  if (!itens?.length) return null
  return (
    <ul className="badges" aria-label="Funcionalidades usadas nesta operação">
      {itens.map((b) => <li key={b.badge} title={b.motivo}><span>{b.badge}</span><small>{b.motivo}</small></li>)}
    </ul>
  )
}

function Gaveta({ titulo = 'Ver query / chamada executada', codigo, children }) {
  const [copiado, setCopiado] = useState(false)
  if (!codigo && !children) return null
  return (
    <details className="gaveta">
      <summary>{titulo}</summary>
      {codigo && (
        <div className="codigo">
          <button type="button" className="copiar" onClick={() => {
            navigator.clipboard?.writeText(codigo); setCopiado(true); setTimeout(() => setCopiado(false), 1400)
          }}>{copiado ? 'copiado ✓' : 'copiar'}</button>
          <pre><code>{codigo}</code></pre>
        </div>
      )}
      {children}
    </details>
  )
}

function Erro({ erro }) {
  if (!erro) return null
  return <p className="aviso erro" role="alert">⚠ {erro}</p>
}

function Stat({ rotulo, valor, sub, tom }) {
  return (
    <div className={`stat ${tom || ''}`}>
      <span className="pov-eyebrow">{rotulo}</span>
      <strong className="pov-stat">{valor}</strong>
      {sub && <small>{sub}</small>}
    </div>
  )
}

const json = (o) => JSON.stringify(o, null, 2)

// ------------------------------------------------------------------ filtros

function Filtros({ f, setF, catalogo, destinos }) {
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: k === 'hora' ? Number(e.target.value) : e.target.value }))
  return (
    <form className="filtros" onSubmit={(e) => e.preventDefault()} aria-label="Filtros da consulta">
      <label>Origem
        <select value={f.origem} onChange={(e) => setF((x) => ({ ...x, origem: e.target.value, destino: '' }))}>
          {catalogo.origens.map((o) => <option key={o.id} value={o.id}>{o.id}{o.nome ? ` · ${o.nome}` : ''}</option>)}
        </select>
      </label>
      <label>Destino
        <select value={f.destino} onChange={set('destino')}>
          {destinos.map((d) => <option key={d.id} value={d.id}>{d.id}{d.comHistorico ? '' : ' (sem histórico)'}</option>)}
        </select>
      </label>
      <label>Tipo de veículo
        <select value={f.tipoVeiculo} onChange={set('tipoVeiculo')}>
          {catalogo.tipos.map((t) => <option key={t._id} value={t._id}>{t._id}</option>)}
        </select>
      </label>
      <label>Hora de partida
        <select value={f.hora} onChange={set('hora')}>
          {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>)}
        </select>
      </label>
      <label>Data de referência (asOf)
        <input type="date" value={f.asOf} onChange={set('asOf')} />
      </label>
    </form>
  )
}

function Contexto({ ctx }) {
  if (!ctx) return null
  const t = ctx.turnoLimites
  return (
    <section className="contexto" aria-label="O que a data de referência define">
      <div><span className="pov-eyebrow">janela [início, fim)</span>
        <b>{ctx.janela.inicioLocal} → {ctx.janela.ultimoDiaIncluido}</b>
        <small>{ctx.janela.dias} dias · fim exclusivo {ctx.janela.fimExclusivoLocal} 00:00 (hoje fica fora)</small></div>
      <div><span className="pov-eyebrow">dia da semana</span>
        <b>{ctx.dow} · {ctx.dowNome}</b><small>1 = domingo · regra {ctx.regraNoite}</small></div>
      <div><span className="pov-eyebrow">turno</span>
        <b>{ctx.turno}</b><small>{String(t.inicioHora).padStart(2, '0')}h–{String(t.fimHora).padStart(2, '0')}h · config v{ctx.configVersao}</small></div>
      <div className="chave"><span className="pov-eyebrow">chave consultada</span>
        <code>{JSON.stringify(ctx.chaveConsultada || {})}</code>
        <small>asOf não filtra o agregado por data: define o “hoje” simulado</small></div>
    </section>
  )
}

// ------------------------------------------------------------------ aba 1

function GradeDowTurno({ docs, chave, nivel, turnos }) {
  const codigos = turnos.map((t) => t.codigo)
  const mapa = Object.fromEntries(docs.map((d) => [`${d.dow}|${d.turno}`, d]))
  const usado = (dow, turno) => (nivel === 'geral' || (nivel === 'turno' && turno === chave.turno) ||
    (nivel === 'dow+turno' && dow === chave.dow && turno === chave.turno))
  return (
    <div className="grade" role="table" aria-label="Documentos do agregado para este trecho e veículo (dow × turno)">
      <div role="row" className="linha cab"><span role="columnheader" />{[1, 2, 3, 4, 5, 6, 7].map((d) => <span role="columnheader" key={d}>{d} {DOW[d]}</span>)}</div>
      {codigos.map((tc) => (
        <div role="row" className="linha" key={tc}>
          <span role="rowheader">{tc}</span>
          {[1, 2, 3, 4, 5, 6, 7].map((dw) => {
            const d = mapa[`${dw}|${tc}`]
            const alvo = chave.dow === dw && chave.turno === tc
            return (
              <span role="cell" key={dw} className={`cel ${d ? 'tem' : 'vazia'} ${alvo ? 'alvo' : ''} ${d && usado(dw, tc) ? 'usada' : ''}`}
                title={d ? `n=${d.n} · média ${fmt(d.mediaMin)} min` : 'sem documento'}>
                {d ? <><b>{fmt(d.mediaMin)}</b><small>n {d.n}</small></> : '·'}
              </span>
            )
          })}
        </div>
      ))}
    </div>
  )
}

function AbaEta({ dados, cfg }) {
  if (!dados) return null
  const r = dados.resultado
  const niveis = ['dow+turno', 'turno', 'geral', 'sem_historico']
  return (
    <div className="aba">
      <div className="resultado">
        <Stat rotulo="tempo médio" valor={r.mediaMin == null ? '—' : `${fmt(r.mediaMin)} min`} sub={r.mediaKm == null ? 'sem histórico no trecho' : `${fmt(r.mediaKm)} km em média`} />
        <Stat rotulo="amostras" valor={int(r.n)} sub={`mínimo ${r.minAmostras}${r.abaixoDoMinimo && r.n ? ' · abaixo do mínimo' : ''}`} tom={r.abaixoDoMinimo ? 'alerta' : ''} />
        <Stat rotulo="docs lidos" valor={int(r.docsLidos)} sub="uma leitura pelo índice único (≤ 21)" />
      </div>
      <ol className="niveis" aria-label="Hierarquia de fallback (proposta para validação com o cliente)">
        {niveis.map((n) => <li key={n} className={n === r.nivel ? 'ativo' : ''} aria-current={n === r.nivel ? 'step' : undefined}>{n === r.nivel ? '● ' : ''}{n}</li>)}
      </ol>
      <p className="nota">Hierarquia <b>proposta para validação com o cliente</b>: dow+turno (n ≥ mínimo) → turno (todos os dias) → geral → sem_historico.</p>
      {r.avisoAsOf && <p className="aviso">⚠ {r.avisoAsOf}</p>}
      <h3>Agregado do trecho/veículo · <code>trecho_media_historica</code></h3>
      <GradeDowTurno docs={dados.documentos} chave={r.chaveSolicitada} nivel={r.nivel} turnos={cfg.turnos} />
      <p className="legenda"><span className="cel alvo mini" /> chave pedida <span className="cel usada mini" /> somada na resposta</p>
      <Badges itens={dados.badges} />
      <Gaveta codigo={dados.mongosh}>
        <pre className="json"><code>{json(r)}</code></pre>
      </Gaveta>
    </div>
  )
}

// ------------------------------------------------------------------ aba 2

function Explain({ titulo, lado }) {
  const e = lado.explain
  return (
    <div className="lado">
      <h3>{titulo}</h3>
      <p className="ns"><code>{lado.consulta.colecao}</code> · {lado.consulta.operacao}</p>
      <dl className="explain">
        <dt>estágio vencedor</dt><dd><code>{e.estagioVencedor}</code></dd>
        <dt>totalKeysExamined</dt><dd className="num">{int(e.totalKeysExamined)}</dd>
        <dt>totalDocsExamined</dt><dd className="num">{int(e.totalDocsExamined)}</dd>
        <dt>nReturned</dt><dd className="num">{int(e.nReturned)}</dd>
        <dt>executionTimeMillis</dt><dd className="num">{int(e.executionTimeMillis)} ms</dd>
        <dt>latência no cliente</dt><dd className="num">{fmt(lado.latenciaClienteMs, 2)} ms</dd>
      </dl>
      <p className="resp">{lado.nivel} · <b>{fmt(lado.mediaMin)} min</b> · n {int(lado.n)}</p>
      <Badges itens={lado.badges} />
      <Gaveta codigo={lado.mongosh} />
    </div>
  )
}

function AbaRaw({ f }) {
  const [res, setRes] = useState(null)
  const [erro, setErro] = useState('')
  const [rodando, setRodando] = useState(false)
  const rodar = async () => {
    setRodando(true); setErro('')
    try { setRes(await get('/api/comparar', f)) } catch (e) { setErro(e.message) } finally { setRodando(false) }
  }
  useEffect(() => { setRes(null) }, [f.origem, f.destino, f.tipoVeiculo, f.hora, f.asOf])
  return (
    <div className="aba">
      <div className="acao">
        <button className="primario" onClick={rodar} disabled={rodando}>{rodando ? 'Executando…' : 'Executar as duas com explain("executionStats")'}</button>
        <span className="nota">Mesma pergunta, mesma janela: na raw (calculada agora) e no agregado (lido pronto). O explain só roda sob este clique.</span>
      </div>
      <Erro erro={erro} />
      {res && (
        <>
          <p className={`veredito ${res.mesmaResposta ? 'ok' : 'erro'}`}>{res.mesmaResposta ? '✓ mesma resposta nas duas fontes' : '✗ respostas diferentes — o agregado está desatualizado para este asOf (rode o job)'}</p>
          <div className="lados">
            <Explain titulo="On the fly na raw" lado={res.raw} />
            <Explain titulo="Materializado" lado={res.materializado} />
          </div>
        </>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ aba 3

function Contadores({ s, titulo }) {
  if (!s) return null
  return (
    <div className="contadores">
      <h4>{titulo}</h4>
      <dl>
        <dt>lidos</dt><dd>{int(s.lidos)}</dd>
        <dt>inseridos</dt><dd>{int(s.inseridos)}</dd>
        <dt>atualizados</dt><dd>{int(s.atualizados)}</dd>
        <dt>removidos</dt><dd className={s.removidos ? 'destaque' : ''}>{int(s.removidos)}</dd>
        <dt>duração</dt><dd>{fmt(s.duracaoMs, 0)} ms</dd>
      </dl>
    </div>
  )
}

function ResumoRun({ dados }) {
  if (!dados) return null
  const { run } = dados
  const c1 = run.stats?.camada1, c2 = run.stats?.camada2, sp = run.stats?.simples
  const dias = c1?.diasReprocessados || []
  return (
    <div className="run">
      <p className="ns">run <code>{run.runId}</code> · asOf {run.asOf} · camada {run.camada} · <b className={run.status === 'ok' ? 'ok' : 'erro'}>{run.status}</b></p>
      {sp ? (
        <div className="contadores-par">
          <Contadores titulo="Simples · raw → média ($out, janela inteira)" s={sp} />
        </div>
      ) : (
        <div className="contadores-par">
          <Contadores titulo={`Camada 1 · raw → buckets por ${c1?.granularidade || 'hora'}`} s={c1} />
          <Contadores titulo="Camada 2 · buckets → média" s={c2} />
        </div>
      )}
      {run.stats?.camada1?.tentativas > 1 && <p className="nota">Camada 1 precisou de {run.stats.camada1.tentativas} tentativas (erro transitório).</p>}
      {c1 && (
        <p className="nota">Modo {c1.modo} · {dias.length <= 8 ? `dias reprocessados: ${dias.join(', ')}` : `${dias.length} dias reprocessados (${dias[0]} … ${dias[dias.length - 1]})`}
          {' · '}atrasados detectados pelo watermark: {c1.atrasadosDetectados} (fora de k: <b>{c1.atrasadosForaDaJanelaK}</b>{c1.diasAtrasados?.length ? ` → ${c1.diasAtrasados.join(', ')}` : ''})</p>
      )}
      <Badges itens={dados.badges} />
      {dados.mongosh?.simples && <Gaveta titulo="Ver query / chamada executada · simples" codigo={dados.mongosh.simples} />}
      {dados.mongosh?.camada1 && <Gaveta titulo="Ver query / chamada executada · camada 1" codigo={dados.mongosh.camada1} />}
      {dados.mongosh?.camada2 && <Gaveta titulo="Ver query / chamada executada · camada 2" codigo={dados.mongosh.camada2} />}
    </div>
  )
}

function Historico({ versao }) {
  const [runs, setRuns] = useState([])
  useEffect(() => { get('/api/job_runs', { limit: 10 }).then(setRuns).catch(() => {}) }, [versao])
  return (
    <details className="gaveta">
      <summary>Histórico de job_runs ({runs.length})</summary>
      <div className="tabela-rolagem">
        <table>
          <thead><tr><th>início</th><th>asOf</th><th>camada</th><th>status</th><th>ins/atu/rem</th><th>fora de k</th></tr></thead>
          <tbody>{runs.map((r) => (
            <tr key={r.runId}><td>{r.iniciadoEm?.slice(0, 19).replace('T', ' ')}</td><td>{r.asOf}</td><td>{r.camada}</td>
              <td className={r.status === 'ok' ? 'ok' : 'erro'} title={r.erro || ''}>{r.status}</td>
              <td>{r.stats ? `${int(r.stats.inseridos)} / ${int(r.stats.atualizados)} / ${int(r.stats.removidos)}` : '—'}</td>
              <td>{r.atrasadosForaDaJanelaK ?? '—'}</td></tr>))}</tbody>
        </table>
      </div>
    </details>
  )
}

function BucketD2({ f, versao }) {
  const [b, setB] = useState(null)
  useEffect(() => {
    get('/api/buckets', { origem: f.origem, destino: f.destino, tipoVeiculo: f.tipoVeiculo, asOf: f.asOf, dias: 3 }).then(setB).catch(() => setB(null))
  }, [f.origem, f.destino, f.tipoVeiculo, f.asOf, versao])
  if (!b) return null
  if (b.modoMaterializacao === 'simples') {
    return <p className="nota">Modo simples: não há buckets — cada run relê a janela inteira da raw e troca o agregado com <code>$out</code>. Dado atrasado entra no run seguinte, sem watermark.</p>
  }
  const turno = b.granularidade === 'turno'
  return (
    <div className="buckets">
      <h4>Buckets D-3…D-1 deste trecho/veículo · <code>{b.colecao}</code></h4>
      {b.buckets.length === 0 ? <p className="nota">Nenhum bucket nos últimos 3 dias para esta chave.</p> : (
        <div className="tabela-rolagem"><table>
          <thead><tr><th>dataLocal</th><th>{turno ? 'turno' : 'hora'}</th><th>{turno ? 'dow' : 'dowCivil'}</th><th>n</th><th>somaMin</th><th>min–max</th><th>runId</th></tr></thead>
          <tbody>{b.buckets.map((x) => (
            <tr key={`${x.dataLocal}${x.hora ?? x.turno}${x.dow ?? ''}`}><td>{x.dataLocal.slice(0, 10)}</td><td>{turno ? x.turno : x.hora}</td><td>{turno ? x.dow : x.dowCivil}</td><td>{x.n}</td>
              <td>{fmt(x.somaMin)}</td><td>{fmt(x.minMin)}–{fmt(x.maxMin)}</td><td><code>{x.runId.slice(-4)}</code></td></tr>))}</tbody>
        </table></div>)}
      <Gaveta codigo={b.mongosh} />
    </div>
  )
}

function AbaJob({ f, cfg, aoMudar }) {
  const simples = cfg.modoMaterializacao === 'simples'
  const [camada, setCamada] = useState('todas')
  const [res, setRes] = useState(null)
  const [atraso, setAtraso] = useState(null)
  const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [versao, setVersao] = useState(0)
  const exec = async (fn) => {
    setOcupado(true); setErro('')
    try { await fn(); setVersao((v) => v + 1); aoMudar() } catch (e) { setErro(e.message) } finally { setOcupado(false) }
  }
  return (
    <div className="aba">
      <div className="acao">
        {!simples && (
          <div className="seg" role="group" aria-label="Camada">
            {['1', '2', 'todas'].map((c) => <button key={c} aria-pressed={camada === c} onClick={() => setCamada(c)}>{c === 'todas' ? 'todas' : `camada ${c}`}</button>)}
          </div>)}
        <button className="primario" disabled={ocupado} onClick={() => exec(async () => setRes(await post('/api/job', { asOf: f.asOf, camada: simples ? 'todas' : camada })))}>
          {ocupado ? 'Rodando…' : `Rodar job com asOf ${f.asOf}`}</button>
        <button disabled={ocupado} onClick={() => exec(async () => setAtraso(await post('/api/atrasado', { ...f, diasAtras: 2, hora: 8 })))}>
          Injetar observação atrasada em D-2 (08:00)</button>
      </div>
      <p className="nota">Desenho configurado: <b>{simples ? 'simples' : `incremental por ${cfg.granularidadeBucket}`}</b>. Nem <code>$out</code> nem <code>$merge</code> atualizam nada sozinhos: quem recalcula é o job, agendado de fora. Rodar de novo dá o mesmo resultado ({simples ? '$out troca a collection inteira' : 'whenMatched: "replace" recalcula a chave inteira'}).</p>
      <Erro erro={erro} />
      {atraso && (
        <div className="aviso">Inserida em <code>trecho_observacoes</code>: partida {atraso.inserido.observadoEm} · {fmt(atraso.inserido.tempoMin)} min · ingeridoEm {atraso.inserido.ingeridoEm} (relógio simulado da demo). Rode o job: {simples ? 'o run seguinte relê a janela e a observação entra' : 'o dia D-2 é reprocessado'}; rode uma terceira vez para ver “inseridos 0”.
          <Gaveta codigo={atraso.comando} /></div>
      )}
      <ResumoRun dados={res} />
      <BucketD2 f={f} versao={versao} />
      <Historico versao={versao} />
    </div>
  )
}

// ------------------------------------------------------------------ aba 4

function Dias({ lista, sai, entra }) {
  return (
    <ol className="dias">
      {lista.map((d) => (
        <li key={d.dia} className={`${d.dia === sai ? 'sai' : ''} ${d.dia === entra ? 'entra' : ''} ${d.buckets ? '' : 'vazio'}`}>
          <span>{d.dia.slice(5)}</span><b>{int(d.obs)}</b><small>{d.dia === sai ? '← saiu' : d.dia === entra ? 'entrou →' : `${int(d.buckets)} bk`}</small>
        </li>))}
    </ol>
  )
}

function AbaJanela({ f, setF, cfg, aoMudar }) {
  const [jan, setJan] = useState(null)
  const [passo, setPasso] = useState(null)
  const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const carregar = useCallback(() => get('/api/janela', { asOf: f.asOf }).then(setJan).catch((e) => setErro(e.message)), [f.asOf])
  useEffect(() => { carregar() }, [carregar])
  const avancar = async () => {
    setOcupado(true); setErro('')
    try {
      const [p] = await post('/api/avancar', { dias: 1 })
      setPasso(p); setF((x) => ({ ...x, asOf: p.asOf })); aoMudar()
    } catch (e) { setErro(e.message) } finally { setOcupado(false) }
  }
  const modo = async (m) => {
    try { await post('/api/config', { mudancas: { modoLimpezaCamada2: m } }); aoMudar(); carregar() } catch (e) { setErro(e.message) }
  }
  const st = passo?.run?.stats || {}
  // a etapa que gera o agregado: camada 2 (incremental) ou o pipeline único (simples)
  const final = st.camada2 || st.simples
  return (
    <div className="aba">
      <div className="acao">
        <button className="primario" disabled={ocupado} onClick={avancar}>{ocupado ? 'Avançando…' : 'Avançar 1 dia'}</button>
        {cfg.modoMaterializacao !== 'simples' && <div className="seg" role="group" aria-label="Limpeza da camada 2">
          {['merge_runid', 'out'].map((m) => <button key={m} aria-pressed={cfg.modoLimpezaCamada2 === m} onClick={() => modo(m)}>{m === 'out' ? '$out' : '$merge + runId'}</button>)}
        </div>}
        <span className="nota">Avançar = gerar o novo “hoje”, liberar atrasados que chegaram e rodar o job com asOf + 1.</span>
      </div>
      <Erro erro={erro} />
      {jan && (
        <div className="timeline" aria-label="Bordas da janela móvel">
          <div><h4>Início da janela · {jan.inicio}</h4><Dias lista={jan.inicioDias} sai={jan.diaQueSaiu} />
            <p className="nota">Os buckets do dia que saiu continuam na camada 1 até o TTL; a camada 2 só deixa de lê-los, e as chaves que dependiam só dele são removidas.</p></div>
          <div><h4>Fim da janela · último dia {jan.diaQueEntrou}</h4><Dias lista={jan.fimDias} entra={jan.diaQueEntrou} />
            <p className="nota">Hoje ({jan.fimExclusivo}): {int(jan.hojeObservacoesNaRaw)} observações na raw, fora das médias.</p></div>
        </div>
      )}
      {passo && (
        <div className="run">
          <p className="ns">asOf {passo.asOf}: +{int(passo.observacoesGeradas)} obs geradas · {int(passo.atrasadosLiberados)} atrasadas chegaram · entrou {passo.diaQueEntra} · saiu {passo.diaQueSai}</p>
          <div className="contadores-par">
            {st.camada1 && <Contadores titulo={`Camada 1 · buckets por ${st.camada1.granularidade || 'hora'}`} s={st.camada1} />}
            {final && <Contadores titulo={st.simples ? 'Simples · raw → média' : `Camada 2 · ${final.modo}`} s={final} />}
          </div>
          {final?.removidosAmostra?.length > 0 && (
            <details className="gaveta" open>
              <summary>Agregados removidos (saíram da janela) · {final.removidos}</summary>
              <ul className="removidos">{final.removidosAmostra.slice(0, 12).map((k) => <li key={JSON.stringify(k)}><code>{k.origem}→{k.destino} {k.tipoVeiculo} dow {k.dow} {k.turno}</code></li>)}</ul>
            </details>)}
          <Badges itens={passo.badges} />
          <Gaveta titulo={`Ver query / chamada executada · ${st.simples ? 'simples' : 'camada 2'}`} codigo={passo.mongosh?.camada2 || passo.mongosh?.simples} />
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ simples × incremental

function AbaModos({ f, aoMudar }) {
  const [res, setRes] = useState(null)
  const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const rodar = async () => {
    setOcupado(true); setErro('')
    try { setRes(await post('/api/comparar-modos', { asOf: f.asOf })); aoMudar() } catch (e) { setErro(e.message) } finally { setOcupado(false) }
  }
  const b = res?.benchmarkEscala
  return (
    <div className="aba">
      <div className="acao">
        <button className="primario" disabled={ocupado} onClick={rodar}>{ocupado ? 'Rodando os dois desenhos…' : `Rodar os dois desenhos com asOf ${f.asOf}`}</button>
        <span className="nota">Mesma raw, mesmo asOf. A config não é alterada; o incremental roda 2× (carga e run diário).</span>
      </div>
      <Erro erro={erro} />
      <div className="lados">
        <div className="lado"><h3>Simples · a “MV com COMPLETE refresh”</h3>
          <p className="nota">raw → <code>$group</code> da janela inteira → <code>$out</code>. Um pipeline, sem buckets, sem watermark: dado atrasado entra no run seguinte. Troca atômica para quem consulta.</p></div>
        <div className="lado"><h3>Incremental · raw → buckets por turno → média</h3>
          <p className="nota">Relê só D-1…D-k e os dias com atraso; a camada 2 soma buckets. Compensa com raw de retenção curta ou volume que torne o recálculo completo caro.</p></div>
      </div>
      {res && (
        <>
          <p className={`veredito ${res.mesmoAgregado ? 'ok' : 'erro'}`}>{res.mesmoAgregado ? `✓ mesmo agregado nos dois desenhos (${int(res.desenhos.simples.documentos)} documentos)` : '✗ agregados diferentes'}</p>
          <div className="lados">
            {Object.entries(res.desenhos).map(([nome, d]) => (
              <div className="lado" key={nome}>
                <h3>{nome === 'simples' ? 'Simples' : 'Incremental por turno'}</h3>
                <table><thead><tr><th>run</th><th>tempo</th><th>raw lida</th><th>buckets lidos</th></tr></thead>
                  <tbody>{d.runs.map((r, i) => (
                    <tr key={r.runId}><td>{nome === 'simples' ? 'diário' : (r.etapas.camada1?.modo || (i ? 'diário' : 'carga'))}</td><td>{fmt(r.segundos, 2)} s</td>
                      <td>{int(r.etapas.simples?.lidos ?? r.etapas.camada1?.lidos)}</td><td>{r.etapas.camada2 ? int(r.etapas.camada2.lidos) : '—'}</td></tr>))}</tbody></table>
                <Badges itens={d.badges} />
              </div>))}
          </div>
          <p className="nota">Agora no banco: raw {int(res.contagens.trecho_observacoes)} · buckets por turno {int(res.contagens.trecho_bucket_turno)} · buckets por hora {int(res.contagens.trecho_bucket_diario)} · médias {int(res.contagens.trecho_media_historica)}.</p>
        </>
      )}
      {b && (
        <details className="gaveta" open={!!res}>
          <summary>Benchmark escala ({int(b.observacoes)} observações, medido em {b.medidoEm?.slice(0, 10)}) · {b.fonte}</summary>
          <p className="nota pad">Simples (janela inteira, <code>$out</code>): <b>{fmt(b.simplesSegundos)} s</b>{b.incremental ? <> · Incremental em regime: <b>{fmt(b.incremental.segundos)} s</b> ({int(b.incremental.rawLidos)} observações relidas)</> : null}. Medido no cluster compartilhado; números de laboratório, não do volume do cliente.</p>
        </details>)}
    </div>
  )
}

// ------------------------------------------------------------------ aba 5

function AbaConfig({ f, cfg, aoMudar }) {
  const [turnos, setTurnos] = useState(cfg.turnos)
  const [regra, setRegra] = useState(cfg.regraNoite)
  const [minimo, setMinimo] = useState(cfg.minAmostras)
  const [modo, setModo] = useState(cfg.modoMaterializacao)
  const [grao, setGrao] = useState(cfg.granularidadeBucket)
  const [comDow, setComDow] = useState(cfg.incluirDow)
  const [res, setRes] = useState(null)
  const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState(false)
  useEffect(() => {
    setTurnos(cfg.turnos); setRegra(cfg.regraNoite); setMinimo(cfg.minAmostras)
    setModo(cfg.modoMaterializacao); setGrao(cfg.granularidadeBucket); setComDow(cfg.incluirDow)
  }, [cfg.versao])
  const setT = (i, k) => (e) => setTurnos((ts) => ts.map((t, j) => (j === i ? { ...t, [k]: Number(e.target.value) } : t)))
  const salvar = async () => {
    setOcupado(true); setErro('')
    try {
      setRes(await post('/api/config', { mudancas: { turnos, regraNoite: regra, minAmostras: Number(minimo), modoMaterializacao: modo, granularidadeBucket: grao, incluirDow: comDow }, rerodarCamada2: true, asOf: f.asOf }))
      aoMudar()
    } catch (e) { setErro(e.message) } finally { setOcupado(false) }
  }
  const prova = res?.provaRawIntacta
  return (
    <div className="aba">
      <div className="config">
        <fieldset><legend>Turnos (hora local; o que cruza a meia-noite tem início ≥ fim)</legend>
          {turnos.map((t, i) => (
            <div className="turno" key={t.codigo}><b>{t.codigo}</b>
              <label>início<input type="number" min="0" max="23" value={t.inicioHora} onChange={setT(i, 'inicioHora')} /></label>
              <label>fim<input type="number" min="0" max="24" value={t.fimHora} onChange={setT(i, 'fimHora')} /></label>
            </div>))}
        </fieldset>
        <fieldset><legend>Regra da noite</legend>
          <div className="seg" role="group" aria-label="Regra da noite">
            {['dia_civil', 'dia_operacional'].map((r) => <button key={r} aria-pressed={regra === r} onClick={() => setRegra(r)}>{r}</button>)}
          </div>
          <p className="nota">dia_operacional: a madrugada (antes do fim do turno noturno) conta no dia anterior — sexta 01:00 vira “sexta à noite”.</p>
          <label>mínimo de amostras <input type="number" min="1" value={minimo} onChange={(e) => setMinimo(e.target.value)} /></label>
        </fieldset>
        <fieldset><legend>Desenho da materialização</legend>
          <div className="seg" role="group" aria-label="Modo">
            {[['simples', 'simples · raw → média'], ['incremental', 'incremental · raw → buckets → média']].map(([v, r]) => <button key={v} aria-pressed={modo === v} onClick={() => setModo(v)}>{r}</button>)}
          </div>
          {modo === 'incremental' && (
            <div className="seg" role="group" aria-label="Grão do bucket">
              {['turno', 'hora'].map((g) => <button key={g} aria-pressed={grao === g} onClick={() => setGrao(g)}>bucket por {g}</button>)}
            </div>)}
          <div className="seg" role="group" aria-label="Dia da semana na chave">
            {[[true, 'turno + dia da semana'], [false, 'só turno (M/T/N)']].map(([v, r]) => <button key={String(v)} aria-pressed={comDow === v} onClick={() => setComDow(v)}>{r}</button>)}
          </div>
        </fieldset>
        <fieldset><legend>O que uma mudança de turno reprocessa</legend>
          <p className="nota"><b>simples</b>: relê a janela da raw (é o desenho).<br /><b>incremental por turno</b>: turno e dow estão gravados no bucket — refaz a camada 1 inteira.<br /><b>incremental por hora</b>: só a camada 2; a raw não é relida.</p>
        </fieldset>
      </div>
      <div className="acao"><button className="primario" disabled={ocupado} onClick={salvar}>{ocupado ? 'Recalculando…' : 'Salvar e recalcular o necessário'}</button>
        <span className="nota">config v{cfg.versao}.</span></div>
      <Erro erro={erro} />
      {prova && (
        <div className="run">
          <div className="resultado">
            <Stat rotulo="desenho" valor={prova.desenho} />
            <Stat rotulo="observações raw lidas" valor={int(prova.observacoesRawLidas)} sub={`raw: ${int(prova.rawDocsAntes)} → ${int(prova.rawDocsDepois)} docs`} tom={prova.observacoesRawLidas ? 'alerta' : ''} />
            <Stat rotulo="buckets lidos" valor={int(prova.bucketsLidos)} sub={prova.camada1Executada ? 'camada 1 refeita' : 'camada 1 não executada'} />
          </div>
          {prova.desenho === 'incremental/hora' && <p className="nota">Último bucket gravado: runId <code>{prova.ultimoBucketRunIdAntes}</code> antes e <code>{prova.ultimoBucketRunIdDepois}</code> depois — nenhum bucket foi reescrito.</p>}
          <ResumoRun dados={res} />
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ capô

function Capo({ f }) {
  const [d, setD] = useState(null)
  const [erro, setErro] = useState('')
  useEffect(() => { get('/api/capo', { asOf: f.asOf }).then(setD).catch((e) => setErro(e.message)) }, [f.asOf])
  if (erro) return <Erro erro={erro} />
  if (!d) return <p className="nota">Lendo listCollections / listIndexes…</p>
  const p = d.pipelines
  return (
    <div className="aba">
      <p className="nota">Pipelines exatamente como o job/consulta enviam com asOf {p.asOf} e config v{p.configVersao}; validators, índices e TTLs lidos do banco agora.</p>
      <Gaveta titulo="Camada 1 · raw → buckets ($merge)" codigo={p.camada1.mongosh} />
      <Gaveta titulo="Camada 2 · buckets → média" codigo={p.camada2.mongosh} />
      <Gaveta titulo="Consulta de fallback" codigo={p.fallback.mongosh} />
      <Gaveta titulo="Equivalente on the fly na raw" codigo={p.rawOnTheFly.mongosh} />
      <h3>Collections · listCollections + listIndexes</h3>
      <div className="tabela-rolagem"><table>
        <thead><tr><th>collection</th><th>docs (estim.)</th><th>validator</th><th>índices</th></tr></thead>
        <tbody>{Object.entries(d.colecoes).map(([nome, c]) => (
          <tr key={nome}><td><code>{nome}</code></td><td>{int(c.docsEstimados)}</td>
            <td>{c.validator ? `$jsonSchema · ${c.validationLevel}/${c.validationAction}` : '—'}</td>
            <td><ul className="idx">{c.indices.map((i) => <li key={i.nome}><code>{JSON.stringify(i.chave)}</code>{i.unique ? ' unique' : ''}{i.ttlSegundos != null ? ` · TTL ${i.ttlSegundos ? `${i.ttlDias} d` : 'expiraEm'}` : ''}</li>)}</ul></td></tr>))}</tbody>
      </table></div>
      {Object.entries(d.colecoes).filter(([, c]) => c.validator).map(([nome, c]) => (
        <Gaveta key={nome} titulo={`Validator de ${nome}`} codigo={json(c.validator)} />))}
    </div>
  )
}

// ------------------------------------------------------------------ app

// Erro de renderização numa aba não derruba a página: o apresentador vê o que houve e troca de aba.
class Contencao extends Component {
  constructor(props) { super(props); this.state = { erro: null } }
  static getDerivedStateFromError(erro) { return { erro } }
  componentDidUpdate(prev) { if (prev.chave !== this.props.chave && this.state.erro) this.setState({ erro: null }) }
  render() {
    if (this.state.erro) return <p className="aviso erro" role="alert">⚠ Esta aba falhou ao exibir o resultado ({String(this.state.erro.message || this.state.erro)}). Troque de aba ou recarregue; os dados no banco não foram afetados.</p>
    return this.props.children
  }
}

export default function App() {
  const [estado, setEstado] = useState(null)
  const [catalogo, setCatalogo] = useState({ origens: [], tipos: [] })
  const [destinos, setDestinos] = useState([])
  const [f, setF] = useState({ origem: '', destino: '', tipoVeiculo: 'BITREM', hora: 20, asOf: '' })
  const [aba, setAba] = useState('eta')
  const [eta, setEta] = useState(null)
  const [erro, setErro] = useState('')
  const [rev, setRev] = useState(0)
  const aoMudar = useCallback(() => setRev((r) => r + 1), [])

  useEffect(() => {
    get('/api/estado').then((e) => {
      setEstado(e); setErro('')
      setF((x) => ({ ...x, asOf: x.asOf || e.asOfAtual || e.hojeReal }))
    }).catch((e) => setErro(e.message))
  }, [rev])
  useEffect(() => {
    get('/api/catalogo').then((c) => {
      setCatalogo(c)
      setF((x) => ({ ...x, origem: x.origem || c.origens[0]?.id || '' }))
    }).catch(() => {})
  }, [estado?.db])
  const ultimaDest = useRef(0)
  useEffect(() => {
    if (!f.origem) return
    const n = ++ultimaDest.current
    get('/api/destinos', { origem: f.origem }).then((ds) => {
      if (n !== ultimaDest.current) return
      setDestinos(ds)
      setF((x) => (ds.some((d) => d.id === x.destino) ? x : { ...x, destino: (ds.find((d) => d.comHistorico) || ds[0])?.id || '' }))
    }).catch(() => {})
  }, [f.origem, rev])
  // Com o banco remoto, respostas podem chegar fora de ordem: só a última pedida vale.
  const ultimaEta = useRef(0)
  useEffect(() => {
    if (!f.origem || !f.destino || !f.asOf) return
    const n = ++ultimaEta.current
    setEta((e) => (e ? { ...e, carregando: true } : e))
    get('/api/eta', f)
      .then((r) => { if (n === ultimaEta.current) { setEta(r); setErro('') } })
      .catch((e) => { if (n === ultimaEta.current) setErro(e.message) })
  }, [f, rev])

  const cfg = estado?.config
  const contagens = estado?.contagens || {}
  // topo mostra só as camadas do desenho configurado (simples: raw → média)
  const camadas = useMemo(() => {
    const raw = ['raw', 'trecho_observacoes', contagens.trecho_observacoes]
    const media = ['média', 'trecho_media_historica', contagens.trecho_media_historica]
    if (!cfg || cfg.modoMaterializacao === 'simples') return [raw, media]
    const turno = cfg.granularidadeBucket === 'turno'
    return [raw, [turno ? 'buckets/turno' : 'buckets/hora', turno ? 'trecho_bucket_turno' : 'trecho_bucket_diario',
      turno ? contagens.trecho_bucket_turno : contagens.trecho_bucket_diario], media]
  }, [contagens, cfg])

  return (
    <div className="app" data-pov-shell>
      <header className="topo">
        <div className="marca"><span className="folha" aria-hidden="true" /><strong>Agregados em janela móvel</strong><span>fallback de ETA · frota</span></div>
        <div className="camadas" aria-label="Volume por camada">
          {camadas.map(([r, n, v], i) => <span key={n} title={n}>{i > 0 && <i aria-hidden="true">→</i>}<b>{int(v)}</b> {r}</span>)}
        </div>
        <div className="conexao" data-ok={estado ? 'true' : 'false'}><span aria-hidden="true" />{estado ? `${estado.db} · MongoDB ${estado.mongodb}` : 'sem backend'}</div>
      </header>

      <main id="conteudo" className="palco">
        <section className="hero pov-motif">
          <p className="pov-eyebrow">equivalente a uma materialized view</p>
          <h1>Média histórica pronta por trecho, veículo, dia e turno</h1>
          <p className="tese">Quando o ETA online cai, o fallback lê a média de D-1…D-{cfg?.janelaDias ?? 180} já calculada: ≤ 21 documentos pelo índice.</p>
        </section>

        {erro && <Erro erro={erro} />}
        {!estado && !erro && <p className="nota">Conectando ao backend…</p>}
        {estado && contagens.trecho_media_historica === 0 && (
          <p className="aviso">Agregado vazio: rode <code>make seed PROFILE=small && make job</code> (ou o botão na aba Job).</p>)}

        {estado && cfg && (
          <>
            <Filtros f={f} setF={setF} catalogo={catalogo} destinos={destinos} />
            <div className={eta?.carregando ? 'atualizando' : ''} aria-busy={eta?.carregando ? 'true' : 'false'}>
              <Contexto ctx={eta?.contexto} />
            </div>
            <nav className="abas" aria-label="Seções">
              {ABAS.map(([id, nome]) => <button key={id} aria-current={aba === id ? 'page' : undefined} onClick={() => setAba(id)}>{nome}</button>)}
              <button className="secundaria" aria-current={aba === 'capo' ? 'page' : undefined} onClick={() => setAba('capo')}>Por baixo do capô</button>
            </nav>
            <section role="tabpanel" className="painel"><Contencao chave={aba}>
              {aba === 'eta' && <div className={eta?.carregando ? 'atualizando' : ''}><AbaEta dados={eta} cfg={cfg} /></div>}
              {aba === 'raw' && <AbaRaw f={f} />}
              {aba === 'modos' && <AbaModos f={f} aoMudar={aoMudar} />}
              {aba === 'job' && <><AbaJob f={f} cfg={cfg} aoMudar={aoMudar} /><h2 className="secao">Janela móvel</h2><AbaJanela f={f} setF={setF} cfg={cfg} aoMudar={aoMudar} /></>}
              {aba === 'config' && <AbaConfig f={f} cfg={cfg} aoMudar={aoMudar} />}
              {aba === 'capo' && <Capo f={f} key={rev} />}
            </Contencao></section>
          </>
        )}
        <footer className="rodape">Dados 100% sintéticos. O modelo de dados desta POV demonstra o padrão; não é proposta de schema produtivo.</footer>
      </main>
    </div>
  )
}

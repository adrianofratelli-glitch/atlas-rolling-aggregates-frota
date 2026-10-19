import { useCallback, useEffect, useRef, useState } from 'react'
import { get, post } from './api.js'
import { ddmm } from './fmt.js'
import { filtroInicial } from './comp/FiltroCenario.jsx'
import ResetDemo, { Progresso } from './comp/ResetDemo.jsx'
import DadoBruto from './passos/DadoBruto.jsx'
import Regra from './passos/Regra.jsx'
import GerarBase from './passos/GerarBase.jsx'
import Cenarios from './passos/Cenarios.jsx'
import ForaDaBase from './passos/ForaDaBase.jsx'
import QuandoAtualiza from './passos/QuandoAtualiza.jsx'
import PoucasAmostras from './passos/PoucasAmostras.jsx'

const PASSOS = [
  { titulo: 'Dado bruto e schema', lead: 'Cada viagem gera observações: quando, quanto andou e quanto demorou.', C: DadoBruto },
  { titulo: 'A regra', lead: 'A média sai dos últimos 180 dias, por trecho, veículo, dia da semana e hora.', C: Regra },
  { titulo: 'Gerar a base', lead: 'Um aggregate lê a raw e grava as médias prontas numa collection.', C: GerarBase },
  { titulo: 'Consultar cenários', lead: 'Qualquer combinação de dias e horas soma poucos documentos já prontos.', C: Cenarios },
  { titulo: 'Fora da base', lead: 'Outro período? Calcula na raw na hora e, se quiser, guarda o resultado.', C: ForaDaBase },
  { titulo: 'Quando atualiza', lead: 'Um trigger agendado roda o job uma vez por dia.', C: QuandoAtualiza },
  { titulo: 'Poucas amostras', lead: 'Trecho com pouco histórico: a consulta amplia até ter amostras suficientes.', C: PoucasAmostras },
]
const ALVO = { atlas: 'MongoDB Atlas', local: 'Docker local' }

const passoDaUrl = () => {
  const n = Number(new URLSearchParams(window.location.hash.slice(1)).get('passo'))
  return Number.isInteger(n) && n >= 1 && n <= PASSOS.length ? n : 1
}

export default function App() {
  const [passo, setPasso] = useState(passoDaUrl)
  const [visitados, setVisitados] = useState(() => new Set([passoDaUrl()]))
  const [estado, setEstado] = useState(null)
  const [opcoes, setOpcoes] = useState(null)
  const [erro, setErro] = useState('')
  const [rev, setRev] = useState(0)
  const [filtro, setFiltro] = useState(null)
  const [reset, setReset] = useState({ resetando: false })
  const titulo = useRef(null)
  const abrirReset = useRef(null)
  const passoAnterior = useRef(passoDaUrl())

  const carregar = useCallback(async () => {
    try {
      const [e, o] = await Promise.all([get('/api/estado'), get('/api/opcoes')])
      setEstado(e); setOpcoes(o); setErro('')
      setFiltro((f) => (f && o.trechos.some((t) => t.origem === f.origem && t.destino === f.destino) ? f : filtroInicial(o)))
      if (e.resetando) setReset((r) => ({ ...r, resetando: true }))
    } catch (e) {
      setErro(e.message)
    }
  }, [])
  useEffect(() => { carregar() }, [carregar])
  const atualizarEstado = useCallback(() => { get('/api/estado').then(setEstado).catch(() => {}) }, [])

  // passo atual na URL (#passo=4); voltar/avançar do navegador também funciona
  useEffect(() => {
    // o link "Pular para o conteúdo" troca o hash para #conteudo: não pode mandar ao passo 1
    const aoMudar = () => {
      if (new URLSearchParams(window.location.hash.slice(1)).has('passo')) setPasso(passoDaUrl())
      else window.history.replaceState(null, '', `#passo=${passoAnterior.current}`)
    }
    window.addEventListener('hashchange', aoMudar)
    return () => window.removeEventListener('hashchange', aoMudar)
  }, [])
  useEffect(() => {
    if (passoDaUrl() !== passo) window.location.hash = `passo=${passo}`
    setVisitados((v) => (v.has(passo) ? v : new Set(v).add(passo)))
    document.querySelector('.trilho [aria-current="step"]')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    // só move o foco quando o passo muda de fato (o StrictMode reexecuta o efeito no load)
    if (passoAnterior.current === passo) return
    passoAnterior.current = passo
    window.scrollTo({ top: 0 })
    titulo.current?.focus({ preventScroll: true })
  }, [passo])

  // reset: acompanha etapa e % a cada ~1 s; ao fim recarrega tudo e remonta o passo
  const iniciarReset = async () => {
    setReset({ resetando: false })
    try {
      await post('/api/reset')
      setReset({ resetando: true, etapa: 'iniciando', pct: 0 })
    } catch (e) {
      if (e.status === 409) {
        const s = await get('/api/reset/status').catch(() => ({}))
        setReset({ ...s, resetando: true, aviso: `Já existe um reset em andamento (etapa: ${s.etapa || '—'}).` })
      } else setReset({ resetando: false, erro: e.message })
    }
  }
  // setTimeout encadeado: com ida e volta lenta (Atlas) as chamadas nunca se sobrepõem
  useEffect(() => {
    if (!reset.resetando) return undefined
    let vivo = true
    let id
    const ciclo = async () => {
      const [s] = await Promise.all([
        get('/api/reset/status').catch(() => null),
        get('/api/estado').then(setEstado).catch(() => {}),
      ])
      if (!vivo) return
      if (s) setReset((r) => ({ ...r, ...s, aviso: s.resetando ? r.aviso : undefined }))
      if (s && !s.resetando) { await carregar(); setRev((n) => n + 1); return }
      id = setTimeout(ciclo, 1000)
    }
    id = setTimeout(ciclo, 1000)
    return () => { vivo = false; clearTimeout(id) }
  }, [reset.resetando, carregar])

  const ir = (n) => setPasso(Math.min(PASSOS.length, Math.max(1, n)))
  const P = PASSOS[passo - 1]
  const proximo = PASSOS[passo]
  const pronto = estado && opcoes && filtro
  const baseVazia = pronto && opcoes.trechos.length === 0

  let corpo
  if (erro && !pronto) {
    corpo = (
      <div className="aviso erro" role="alert">
        <p>{erro}</p>
        <button type="button" onClick={carregar}>Tentar de novo</button>
      </div>
    )
  } else if (!pronto) {
    corpo = <p className="nota" role="status">Conectando ao backend…</p>
  } else if (reset.resetando) {
    corpo = <div className="cartao"><Progresso reset={reset} anunciar={false} /><p className="nota">Os passos voltam quando terminar.</p></div>
  } else if (baseVazia) {
    corpo = (
      <div className="aviso" role="status">
        <p>A base está vazia: não há trechos nem observações.</p>
        <button type="button" className="primario" onClick={() => abrirReset.current?.()}>Resetar demo</button>
      </div>
    )
  } else {
    corpo = (
      <>
        {!estado.ultimoJob && passo !== 3 && (
          <p className="aviso">As médias ainda não foram geradas: rode o passo 3 ou <b>Resetar demo</b>.</p>
        )}
        <P.C key={rev} estado={estado} opcoes={opcoes} filtro={filtro} setFiltro={setFiltro}
          ocupado={reset.resetando} onMudou={atualizarEstado} ir={ir} />
      </>
    )
  }

  return (
    <div className="app" data-pov-shell>
      <header className="topo">
        <div className="marca">
          <span className="folha" aria-hidden="true" />
          <h1>Médias históricas prontas para o fallback de ETA</h1>
        </div>
        {estado && <span className={`chip-alvo ${estado.alvo}`}><span aria-hidden="true" />{ALVO[estado.alvo] || estado.alvo}</span>}
      </header>

      <div className="corpo">
        <nav className="trilho" aria-label="Roteiro da demo">
          <ol>
            {PASSOS.map((p, i) => {
              const n = i + 1
              const atual = n === passo
              const feito = visitados.has(n) && !atual
              return (
                <li key={n}>
                  <button type="button" aria-current={atual ? 'step' : undefined} onClick={() => ir(n)}
                    aria-label={`${n} ${p.titulo}${feito ? ' (visitado)' : ''}`}
                    className={feito ? 'feito' : ''}>
                    <span className="n" aria-hidden="true">{feito ? '✓' : n}</span>
                    <span>{p.titulo}</span>
                  </button>
                </li>
              )
            })}
          </ol>
          <div className="trilho-pe">
            {estado?.simuladoAte && <span className="nota">ingestão simulada programada até {ddmm(estado.simuladoAte)}</span>}
            <ResetDemo reset={reset} onConfirmar={iniciarReset} abrirRef={abrirReset} />
          </div>
        </nav>

        <main id="conteudo" className="palco" tabIndex={-1}>
          <header className="passo-cab">
            <p className="pov-eyebrow">Passo {passo} de {PASSOS.length}</p>
            <h2 ref={titulo} tabIndex={-1}>{P.titulo}</h2>
            <p className="lead">{P.lead}</p>
          </header>
          <div className="passo">{corpo}</div>
          <nav className="navpassos" aria-label="Anterior e próximo passo">
            <button type="button" onClick={() => ir(passo - 1)} disabled={passo === 1}>← Anterior</button>
            {proximo
              ? <button type="button" onClick={() => ir(passo + 1)}>Próximo: {proximo.titulo} →</button>
              : <button type="button" onClick={() => ir(1)}>Voltar ao início</button>}
          </nav>
          <footer className="rodape">Dados 100% sintéticos. Modelo de referência: adapte ao cadastro mestre real.</footer>
        </main>
      </div>
    </div>
  )
}

import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { int } from '../fmt.js'

// Mapa do fluxo no topo de cada passo: SVG inline, sem biblioteca. Três desenhos fixos
// (horizontal, médio e vertical) escolhidos pela largura do contêiner, para o texto nunca
// ficar abaixo de ~11 px efetivos nem estourar a largura. `ativo` acende nós e setas pelo id;
// `parcial` deixa em opacidade média; enquanto `animar` for verdadeiro (o job em execução),
// os pontos andam da raw para a base em ciclos; `numeros` ({raw, base}) aparece quando para.

const NOS = {
  rastreio: { titulo: 'Rastreio da frota', sub: ['GPS / TMS — na demo:', 'gerador'] },
  cadastro: { titulo: 'pontos · trechos', mono: true, sub: ['cadastro'] },
  raw: { titulo: 'trecho_observacoes', mono: true, sub: ['raw · uma viagem', 'por documento'] },
  job: { titulo: 'Job', sub: ['Scheduled Trigger', 'ou botão do passo 3'] },
  base: { titulo: 'trecho_media_dow_hora', mono: true, sub: ['base pronta ·', 'materialized view'] },
  eta: { titulo: 'ETA de fallback', sub: ['lê documentos', 'prontos'] },
  salvas: { titulo: 'consultas_salvas', mono: true, sub: ['cache com TTL'] },
}
const NOME = { rastreio: 'rastreio da frota', cadastro: 'cadastro pontos e trechos', raw: 'trecho_observacoes',
  job: 'job diário', base: 'trecho_media_dow_hora', eta: 'ETA de fallback', salvas: 'consultas_salvas' }

const S = (t) => ({ t })
const M = (t) => ({ t, mono: true })
const H_NO = 62

// Coordenadas no espaço do viewBox. Setas: lista de pontos (cotovelos retos).
const LAYOUTS = {
  h: {
    w: 1020, h: 182, fs: { t: 14.5, m: 13, s: 12.5, l: 12.5 },
    nos: { rastreio: [0, 8, 160], cadastro: [0, 110, 160], raw: [200, 56, 172], job: [412, 8, 160],
      base: [636, 8, 188], eta: [864, 56, 150], salvas: [520, 110, 170] },
    setas: {
      'rastreio-raw': { p: [[160, 39], [180, 39], [180, 77], [200, 77]] },
      'cadastro-raw': { p: [[160, 141], [180, 141], [180, 99], [200, 99]], tracejada: true,
        rotulo: { x: 188, y: 136, a: 'start', linhas: [[S('nomes e pares válidos')]] } },
      'raw-job': { p: [[372, 74], [392, 74], [392, 39], [412, 39]] },
      'job-base': { p: [[572, 39], [636, 39]], rotulo: { x: 604, y: 31, a: 'middle', linhas: [[M('$merge')]] } },
      'base-eta': { p: [[824, 39], [939, 39], [939, 56]] },
      'raw-salvas': { p: [[372, 100], [392, 100], [392, 141], [520, 141]],
        rotulo: { x: 456, y: 120, a: 'middle', linhas: [[S('fora da base')], [M('$merge')]] } },
      'salvas-eta': { p: [[690, 141], [939, 141], [939, 118]] },
    },
    numeros: { raw: { x: 286, y: 46, a: 'middle' }, base: { x: 730, y: 92, a: 'middle' } },
  },
  m: {
    w: 540, h: 282, fs: { t: 14, m: 12.5, s: 12.5, l: 12.5 },
    nos: { rastreio: [0, 8, 150], cadastro: [0, 110, 150], raw: [190, 44, 172], job: [398, 8, 142],
      base: [360, 110, 180], salvas: [196, 212, 160], eta: [390, 212, 150] },
    setas: {
      'rastreio-raw': { p: [[150, 39], [170, 39], [170, 65], [190, 65]] },
      'cadastro-raw': { p: [[150, 141], [170, 141], [170, 95], [190, 95]], tracejada: true,
        rotulo: { x: 0, y: 192, a: 'start', linhas: [[S('nomes e pares válidos')]] } },
      'raw-job': { p: [[362, 60], [380, 60], [380, 39], [398, 39]] },
      'job-base': { p: [[450, 70], [450, 110]], rotulo: { x: 458, y: 94, a: 'start', linhas: [[M('$merge')]] } },
      'base-eta': { p: [[465, 172], [465, 212]] },
      'raw-salvas': { p: [[276, 106], [276, 212]],
        rotulo: { x: 268, y: 150, a: 'end', linhas: [[S('fora da base')], [M('$merge')]] } },
      'salvas-eta': { p: [[356, 243], [390, 243]] },
    },
    numeros: { raw: { x: 276, y: 36, a: 'middle' }, base: { x: 457, y: 196, a: 'end' } },
  },
  v: {
    w: 330, h: 380, fs: { t: 13.5, m: 11.5, s: 11.5, l: 11.5 }, numerosDentro: true,
    nos: { rastreio: [0, 8, 160], cadastro: [170, 8, 160], raw: [0, 114, 160], job: [170, 114, 160],
      salvas: [0, 212, 160], base: [170, 212, 160], eta: [85, 310, 160] },
    setas: {
      'rastreio-raw': { p: [[40, 70], [40, 114]] },
      'cadastro-raw': { p: [[250, 70], [250, 84], [130, 84], [130, 114]], tracejada: true,
        rotulo: { x: 138, y: 100, a: 'start', linhas: [[S('nomes e pares válidos')]] } },
      'raw-job': { p: [[160, 145], [170, 145]] },
      'job-base': { p: [[250, 176], [250, 212]], rotulo: { x: 258, y: 198, a: 'start', linhas: [[M('$merge')]] } },
      'base-eta': { p: [[250, 274], [250, 292], [195, 292], [195, 310]] },
      'raw-salvas': { p: [[80, 176], [80, 212]],
        rotulo: { x: 88, y: 198, a: 'start', linhas: [[S('fora da base · '), M('$merge')]] } },
      'salvas-eta': { p: [[80, 274], [80, 292], [135, 292], [135, 310]] },
    },
  },
}
const ROTULO_NUM = { raw: 'lidas', base: 'gravadas' }

const escolher = (largura) => (largura >= 940 ? 'h' : largura >= 480 ? 'm' : 'v')
const reduzido = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
const d = (pts) => pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x} ${y}`).join(' ')

// ponto a uma fração `f` do comprimento de uma polilinha
function ponto(pts, f) {
  const seg = pts.slice(1).map((q, i) => Math.hypot(q[0] - pts[i][0], q[1] - pts[i][1]))
  let resto = f * seg.reduce((a, b) => a + b, 0)
  for (let i = 0; i < seg.length; i++) {
    if (resto <= seg[i] || i === seg.length - 1) {
      const k = seg[i] ? Math.min(1, resto / seg[i]) : 0
      return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * k, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * k]
    }
    resto -= seg[i]
  }
  return pts[pts.length - 1]
}

const DUR = 1400
const PONTOS = 6
const PASSO_MS = 110
const VIAGEM_MS = DUR - PASSO_MS * (PONTOS - 1) - 50
const suave = (x) => 1 - (1 - x) ** 3

function Rotulo({ r, fs }) {
  return (
    <text x={r.x} y={r.y} textAnchor={r.a} className="mf-rotulo" fontSize={fs.l}>
      {r.linhas.map((linha, i) => (
        <tspan key={i} x={r.x} dy={i ? fs.l * 1.3 : 0}>
          {linha.map((p, j) => <tspan key={j} className={p.mono ? 'mf-mono' : undefined}>{p.t}</tspan>)}
        </tspan>
      ))}
    </text>
  )
}

export default function MapaFluxo({ ativo = [], parcial = [], numeros, animar = false, horario, destaqueHorario = false }) {
  const caixa = useRef(null)
  const [tipo, setTipo] = useState('h')
  const [anim, setAnim] = useState(null)
  const uid = useId().replace(/:/g, '')

  useLayoutEffect(() => {
    const el = caixa.current
    if (!el) return undefined
    const medir = () => {
      const cs = getComputedStyle(el)
      setTipo(escolher(el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)))
    }
    medir()
    const ro = new ResizeObserver(medir)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    if (!animar || reduzido()) return undefined
    let id
    const ini = performance.now()
    // ciclos de DUR ms até a resposta chegar (animar vira falso) ou dar erro
    const quadro = (agora) => {
      setAnim((agora - ini) % DUR)
      id = requestAnimationFrame(quadro)
    }
    setAnim(0)
    id = requestAnimationFrame(quadro)
    return () => { cancelAnimationFrame(id); setAnim(null) }
  }, [animar])

  const L = LAYOUTS[tipo]
  const on = new Set(ativo)
  const meio = new Set(parcial)
  const estado = (id) => (on.has(id) ? 'on' : meio.has(id) ? 'meio' : 'off')
  const mostrarNum = numeros && anim === null
  const hor = horario || '03:10'

  const acesos = Object.keys(NOS).filter((n) => on.has(n)).map((n) => NOME[n])
  const parciais = Object.keys(NOS).filter((n) => !on.has(n) && meio.has(n)).map((n) => NOME[n])
  const rotuloAria = 'Mapa do fluxo: o rastreio da frota grava cada viagem em trecho_observacoes, com nomes e pares '
    + `validados pelo cadastro de pontos e trechos; o job das ${hor} lê a raw e grava com $merge em `
    + 'trecho_media_dow_hora; o ETA de fallback lê a base pronta ou, fora da base, calcula na raw e guarda em '
    + `consultas_salvas.${acesos.length ? ` Em destaque neste passo: ${acesos.join(', ')}.` : ''}`
    + (parciais.length ? ` Parcialmente: ${parciais.join(', ')}.` : '')
    + (mostrarNum ? ` Última execução: ${int(numeros.raw)} observações lidas, ${int(numeros.base)} médias gravadas.` : '')

  // trajeto dos pontos: sai da raw, atravessa o job e entra na base
  const trajeto = [...L.setas['raw-job'].p, ...L.setas['job-base'].p]

  return (
    <div ref={caixa} className="mapa-fluxo">
      <svg viewBox={`0 0 ${L.w} ${L.h}`} role="img" aria-label={rotuloAria}
        style={{ maxWidth: `${L.w}px` }} className={`mf-${tipo}`}>
        <defs>
          {['on', 'meio', 'off'].map((s) => (
            <marker key={s} id={`${uid}-${s}`} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7"
              orient="auto-start-reverse">
              <path d="M0 0 8 4 0 8z" className={`mf-ponta ${s}`} />
            </marker>
          ))}
        </defs>

        {Object.entries(L.setas).map(([id, s]) => {
          const st = estado(`e-${id}`)
          return (
            <g key={id} className={`mf-seta ${st}`}>
              <path d={d(s.p)} fill="none" strokeDasharray={s.tracejada ? '5 4' : undefined}
                markerEnd={`url(#${uid}-${st})`} />
              {s.rotulo && <Rotulo r={s.rotulo} fs={L.fs} />}
            </g>
          )
        })}

        {Object.entries(L.nos).map(([id, [x, y, w]]) => {
          const n = NOS[id]
          const st = estado(id)
          const num = L.numerosDentro && mostrarNum && numeros[id] != null
          const sub = num ? [] : n.sub
          return (
            <g key={id} className={`mf-no ${st}`}>
              <rect x={x} y={y} width={w} height={H_NO} rx="10" />
              <text x={x + 10} y={y + 22} className={n.mono ? 'mf-titulo mf-mono' : 'mf-titulo'}
                fontSize={n.mono ? L.fs.m : L.fs.t}>
                {id === 'job'
                  ? <>Job <tspan className={destaqueHorario ? 'mf-hora destaque' : 'mf-hora'}>{hor}</tspan></>
                  : n.titulo}
              </text>
              {sub.map((l, i) => (
                <text key={i} x={x + 10} y={y + 40 + i * 14} className="mf-sub" fontSize={L.fs.s}>{l}</text>
              ))}
              {num && (
                <text x={x + 10} y={y + 44} className="mf-num" fontSize={L.fs.m}>
                  {int(numeros[id])} {ROTULO_NUM[id]}
                </text>
              )}
              {st !== 'off' && (
                // marcador de forma, além da cor: círculo com ✓ (aceso) ou só o anel (parcial), na borda de cima
                <g className="mf-marca" transform={`translate(${x + w - 10} ${y})`}>
                  <circle r="6" />
                  {st === 'on' && <path d="M-3 0 -1 2.2 3 -2.2" />}
                </g>
              )}
            </g>
          )
        })}

        {!L.numerosDentro && mostrarNum && Object.entries(L.numeros).map(([id, p]) => (
          numeros[id] == null ? null : (
            <text key={id} x={p.x} y={p.y} textAnchor={p.a} className="mf-num" fontSize={L.fs.m}>
              {int(numeros[id])} {ROTULO_NUM[id]}
            </text>
          )
        ))}

        {anim !== null && Array.from({ length: PONTOS }, (_, i) => {
          const f = (anim - i * PASSO_MS) / VIAGEM_MS
          if (f <= 0 || f >= 1) return null
          const [cx, cy] = ponto(trajeto, suave(f))
          return <circle key={i} cx={cx} cy={cy} r="4.5" className="mf-particula" />
        })}
      </svg>
    </div>
  )
}

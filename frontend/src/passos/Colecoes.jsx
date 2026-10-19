import { useEffect, useState } from 'react'
import { get } from '../api.js'
import { int } from '../fmt.js'
import GavetaQuery from '../comp/GavetaQuery.jsx'
import MapaFluxo from '../comp/MapaFluxo.jsx'

const DIA_S = 86400
const ATIVO = ['rastreio', 'cadastro', 'raw', 'e-rastreio-raw', 'e-cadastro-raw']

// Tipo do campo, lido do validator que está valendo no banco.
function tipo(p) {
  if (!p) return '—'
  if (p.enum) return p.enum.join(' | ')
  const t = Array.isArray(p.bsonType) ? 'number' : p.bsonType
  return t + (p.exclusiveMinimum ? ' > 0' : p.minimum != null && t !== 'string' ? ` ≥ ${p.minimum}` : '')
}

function Indice({ i }) {
  return (
    <li>
      <code>{Object.keys(i.chave).join(' + ')}</code>
      {i.unico && <span className="tag">único</span>}
      {i.ttlSegundos != null && <span className="tag">TTL {i.ttlSegundos >= DIA_S ? `${Math.round(i.ttlSegundos / DIA_S)} dias` : 'na data do campo'}</span>}
      {i.porque && <span className="porque">{i.porque}</span>}
    </li>
  )
}

function Colecao({ c, aberta }) {
  return (
    <details className="colecao" open={aberta}>
      <summary>
        <code className="nome">{c.nome}</code>
        <span className="papel">{c.papel}</span>
        {c.docs != null && <span className="tag">{int(c.docs)} docs</span>}
      </summary>
      <div className="colecao-corpo">
        <dl className="meta">
          <div><dt>quem grava</dt><dd>{c.grava}</dd></div>
          <div><dt>quem lê</dt><dd>{c.le}</dd></div>
          <div><dt>retenção</dt><dd>{c.retencao}</dd></div>
        </dl>
        <h4>Campos <small>tipos conforme o $jsonSchema validado pelo banco</small></h4>
        <ul className="campos-desc">
          {c.campos.map((k) => (
            <li key={k.nome}>
              <code>{k.nome}</code>
              <span className="tipo">{tipo(k.schema)}{k.schema && !k.obrigatorio ? ' · opcional' : ''}</span>
              <span className="desc">{k.descricao}</span>
            </li>
          ))}
        </ul>
        {c.indices.length > 0 && (
          <>
            <h4>Índices</h4>
            <ul className="indices">{c.indices.map((i) => <Indice key={i.nome} i={i} />)}</ul>
          </>
        )}
        {c.exemplo && (
          <>
            <h4>Formato de um documento <small>ilustrativo, não é uma linha real</small></h4>
            <pre tabIndex={0} aria-label={`Formato de um documento de ${c.nome}`}><code>{JSON.stringify(c.exemplo, null, 2)}</code></pre>
          </>
        )}
      </div>
    </details>
  )
}

export default function Colecoes({ ocupado, estado }) {
  const [d, setD] = useState(null)
  const [erro, setErro] = useState('')
  useEffect(() => {
    if (ocupado) return
    get('/api/colecoes').then((r) => { setD(r); setErro('') }).catch((e) => setErro(e.message))
  }, [ocupado])
  const mapa = <MapaFluxo ativo={ATIVO} horario={estado?.trigger?.horarioLocal} />
  if (erro) return <>{mapa}<p className="aviso erro" role="alert">{erro}</p></>
  if (!d) return <>{mapa}<p className="nota">Carregando as collections…</p></>
  return (
    <>
      {mapa}
      <p className="nota">São {d.colecoes.length} collections. Aqui está o contrato de cada uma, sem amostra de dados:
        o que guarda, quem grava, o que cada campo significa e por que cada índice existe.</p>
      <div className="colecoes">
        {d.colecoes.map((c, i) => <Colecao key={c.nome} c={c} aberta={i < 2} />)}
      </div>
      <GavetaQuery query={null} extra={d.ingestao && {
        titulo: 'Como a ingestão grava', sub: 'exemplo', query: d.ingestao,
        frase: 'Em produção quem grava é o rastreio da frota; o índice único viagemId+seq impede duplicar uma viagem.',
      }} />
    </>
  )
}

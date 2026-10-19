import { useState } from 'react'

const escapar = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
const reEsc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// Destaca só os operadores listados em `operadores`, como token inteiro:
// `$in` não pode acender dentro de `"$inicio"`.
export function destacar(texto, operadores) {
  const html = escapar(texto || '')
  const ops = [...new Set((operadores || []).map((o) => o.op))].sort((a, b) => b.length - a.length)
  if (!ops.length) return html
  const re = new RegExp(`(^|[^\\w$])(${ops.map(reEsc).join('|')})(?![\\w$])`, 'g')
  return html.replace(re, (_, antes, op) => `${antes}<mark>${op}</mark>`)
}

function Chips({ rotulo, itens }) {
  return (
    <span className="chips">
      <span className="chips-rotulo">{rotulo}</span>
      {itens?.length ? itens.map((c) => <code key={c} className="chip">{c}</code>)
        : <span className="chip vazio">nada</span>}
    </span>
  )
}

function Bloco({ query }) {
  const [copiado, setCopiado] = useState('')
  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(query.mongosh)
      setCopiado('copiado ✓')
    } catch {
      setCopiado('não deu para copiar')
    }
    setTimeout(() => setCopiado(''), 1600)
  }
  return (
    <>
      <div className="gaveta-ns">
        <Chips rotulo="Lê de" itens={query.le} />
        <Chips rotulo="Grava em" itens={query.grava} />
      </div>
      <div className="codigo">
        <div className="codigo-cab">
          <span className="nota">mongosh · {query.operacao}</span>
          <button type="button" className="copiar" onClick={copiar} aria-live="polite">{copiado || 'copiar'}</button>
        </div>
        <pre tabIndex={0} aria-label={`Comando ${query.operacao} para o mongosh`}>
          <code dangerouslySetInnerHTML={{ __html: destacar(query.mongosh, query.operadores) }} />
        </pre>
      </div>
      {query.operadores?.length > 0 && (
        <ul className="ops">
          {query.operadores.map((o) => (
            <li key={o.op}><mark>{o.op}</mark><span aria-hidden="true">→</span><span>{o.explicacao}</span></li>
          ))}
        </ul>
      )}
    </>
  )
}

// `extra`: seção adicional com título, frase e outro comando (ex.: como a ingestão grava).
export default function GavetaQuery({ query, geradoPor, extra }) {
  if (!query && !extra) return null
  return (
    <details className="gaveta">
      <summary>{query ? 'Ver query / chamada executada' : 'Ver o exemplo de ingestão'}</summary>
      <div className="gaveta-corpo">
        {query && <Bloco query={query} />}
        {geradoPor && (
          <section className="gerado" aria-label="Como essa base foi gerada">
            <h4>Como essa base foi gerada <small>job diário</small></h4>
            <Bloco query={geradoPor} />
          </section>
        )}
        {extra && (
          <section className="gerado" aria-label={extra.titulo}>
            <h4>{extra.titulo} {extra.sub && <small>{extra.sub}</small>}</h4>
            {extra.frase && <p className="nota">{extra.frase}</p>}
            <Bloco query={extra.query} />
          </section>
        )}
      </div>
    </details>
  )
}

import { useEffect, useState } from 'react'
import { get } from '../api.js'
import { dataLocal, diaSemana, horaLocal, num } from '../fmt.js'
import GavetaQuery from '../comp/GavetaQuery.jsx'
import MapaFluxo from '../comp/MapaFluxo.jsx'

const DIA_S = 86400
const ATIVO = ['rastreio', 'cadastro', 'raw', 'e-rastreio-raw', 'e-cadastro-raw']

// O porquê de cada índice da raw, em uma frase.
function porque(i) {
  if (i.nome === '_id_') return 'identificador de cada documento (padrão do MongoDB).'
  if (i.ttlSegundos != null) return `TTL: o próprio banco apaga a observação após ${Math.round(i.ttlSegundos / DIA_S)} dias.`
  if (i.unico && i.chave.viagemId) return 'impede gravar a mesma observação duas vezes.'
  if (i.chave.observadoEm && i.chave.origem) return 'cenários fora da base: rota + período direto na raw.'
  return ''
}

function tipo(p) {
  if (p.enum) return p.enum.join(' | ')
  const t = Array.isArray(p.bsonType) ? 'number' : p.bsonType
  return t + (p.exclusiveMinimum ? ' > 0' : p.minimum != null && t !== 'string' ? ` ≥ ${p.minimum}` : '')
}

export default function DadoBruto({ ocupado, opcoes, estado }) {
  const [d, setD] = useState(null)
  const [erro, setErro] = useState('')
  useEffect(() => {
    if (ocupado) return
    get('/api/raw').then((r) => { setD(r); setErro('') }).catch((e) => setErro(e.message))
  }, [ocupado])
  const mapa = <MapaFluxo ativo={ATIVO} horario={estado?.trigger?.horarioLocal} />
  if (erro) return <>{mapa}<p className="aviso erro" role="alert">{erro}</p></>
  if (!d) return <>{mapa}<p className="nota">Carregando a amostra…</p></>
  const js = d.schema.validator?.$jsonSchema
  const req = new Set(js?.required || [])
  const t = opcoes?.trechos.find((x) => x.origem === d.filtro.origem && x.destino === d.filtro.destino)
  return (
    <>
      {mapa}
      <div className="duas">
        <section className="cartao">
          <h3>Observações de viagem <small><code>trecho_observacoes</code></small></h3>
          <p className="trecho-nome">{t ? `${t.nomeOrigem} → ${t.nomeDestino}` : `${d.filtro.origem} → ${d.filtro.destino}`} · {d.filtro.tipoVeiculo}
            <small>{d.filtro.origem} → {d.filtro.destino} · amostra de {d.amostra.length} observações</small></p>
          <div className="rolagem" tabIndex={0} aria-label="Amostra da raw">
            <table>
              <thead><tr><th>data local</th><th>dia</th><th>hora</th><th className="dir">km</th><th className="dir">min</th></tr></thead>
              <tbody>
                {d.amostra.map((x) => (
                  <tr key={x._id}>
                    <td>{dataLocal(x.observadoEm)}</td><td>{diaSemana(x.observadoEm)}</td>
                    <td>{horaLocal(x.observadoEm)}</td>
                    <td className="dir">{num(x.distanciaKm)}</td><td className="dir">{num(x.tempoMin)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section className="cartao">
          <h3>Schema validado <small>$jsonSchema</small></h3>
          {js && (
            <ul className="campos">
              {Object.entries(js.properties).map(([k, p]) => (
                <li key={k}><code>{k}</code><span>{tipo(p)}{req.has(k) ? '' : ' (opcional)'}</span></li>
              ))}
            </ul>
          )}
          <h4>Índices</h4>
          <ul className="indices">
            {d.schema.indices.map((i) => (
              <li key={i.nome}>
                <code>{Object.keys(i.chave).join(' + ')}</code>
                {i.unico && <span className="tag">único</span>}
                {i.ttlSegundos != null && <span className="tag">TTL</span>}
                <span className="porque">{porque(i)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
      <GavetaQuery query={d.query} extra={d.ingestao && {
        titulo: 'Como a ingestão grava', sub: 'exemplo', query: d.ingestao,
        frase: 'Em produção quem grava é o rastreio da frota; o índice único viagemId+seq impede duplicar uma viagem.',
      }} />
    </>
  )
}

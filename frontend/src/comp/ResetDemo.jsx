import { useRef, useState } from 'react'

const ETAPAS = {
  iniciando: 'preparando', apagando: 'apagando os dados', gerando: 'gerando as observações',
  inserindo: 'gravando a raw', job: 'rodando o job diário', pronto: 'pronto',
}
export const nomeEtapa = (e) => ETAPAS[e] || e || 'preparando'

export function Progresso({ reset }) {
  const pct = Math.round((reset.pct || 0) * 100)
  return (
    <div className="progresso" role="status" aria-live="polite">
      <span>Recriando a demo · {nomeEtapa(reset.etapa)} · {pct}%</span>
      <progress max="100" value={pct} aria-label="Progresso do reset">{pct}%</progress>
    </div>
  )
}

// Botão discreto no rodapé do trilho; o diálogo mostra a data/hora do clique.
export default function ResetDemo({ reset, onConfirmar, abrirRef }) {
  const dlg = useRef(null)
  const [clique, setClique] = useState('')
  const abrir = () => {
    setClique(new Date().toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'medium' }))
    dlg.current?.showModal()
  }
  if (abrirRef) abrirRef.current = abrir
  return (
    <div className="reset">
      {reset.resetando ? <Progresso reset={reset} /> : (
        <button type="button" className="discreto" onClick={abrir}>Resetar demo</button>
      )}
      {reset.erro && <p className="aviso erro" role="alert">Reset falhou: {reset.erro}</p>}
      {reset.aviso && <p className="aviso" role="status">{reset.aviso}</p>}
      <dialog ref={dlg} className="dialogo" aria-labelledby="reset-titulo">
        <form method="dialog">
          <h3 id="reset-titulo">Recriar a demo?</h3>
          <p>Apaga os dados simulados e gera tudo de novo com referência em <b>{clique}</b>;
            no fim, roda o job diário. Leva alguns segundos.</p>
          <div className="dialogo-acoes">
            <button value="cancelar" className="discreto">Cancelar</button>
            <button value="ok" className="primario" onClick={(e) => { e.preventDefault(); dlg.current.close(); onConfirmar() }}>
              Resetar demo
            </button>
          </div>
        </form>
      </dialog>
    </div>
  )
}

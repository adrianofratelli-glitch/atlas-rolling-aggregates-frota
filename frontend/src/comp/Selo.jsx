// Origem do número: cor nunca sozinha — sempre ícone + texto + a linha de detalhe.
const SELOS = {
  job_diario: {
    rotulo: 'Job diário',
    icone: (
      <svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="currentColor" strokeWidth="1.6" /><path d="M2 6.5h12M5 1.5v3M11 1.5v3" stroke="currentColor" strokeWidth="1.6" /><path d="m5.5 10 1.8 1.7L10.8 8" fill="none" stroke="currentColor" strokeWidth="1.6" /></svg>
    ),
  },
  sob_demanda: {
    rotulo: 'Sob demanda',
    icone: (
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M9 1.5 3.5 9H8l-1 5.5L12.5 7H8z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" /></svg>
    ),
  },
}

export default function Selo({ selo, detalhe }) {
  const s = SELOS[selo]
  if (!s) return null
  return (
    <div className="selo-linha">
      <span className={`selo ${selo}`}>{s.icone}{s.rotulo}</span>
      {detalhe && <span className="selo-detalhe">{detalhe}</span>}
    </div>
  )
}

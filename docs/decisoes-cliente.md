# Decisões a confirmar com o cliente

A POV escolhe um valor padrão para cada item e o isola num ponto do código
(`frota/settings.py` e módulos citados). Nenhum desses valores é recomendação de produção
sem a validação do time de operação. O modelo de dados é de **referência**: adapte ao
cadastro mestre real.

| # | Decisão | Padrão da POV | Onde mudar | Impacto de mudar |
|---|---|---|---|---|
| 1 | Faixas de hora (atalhos) | Manhã 06–12, Tarde 12–18, Noite 18–06, semiabertas `[início, fim)` | `frota/janela.py::ATALHOS` | Só atalhos da UI: a base guarda hora a hora, então qualquer faixa responde sem reprocessar nada. |
| 2 | Mínimo de amostras | 5 | `settings.MIN_AMOSTRAS` | Define quando a consulta na base amplia o recorte. |
| 3 | Hierarquia de ampliação | dias e horas pedidos → todos os dias nas mesmas horas → dia inteiro nos dias pedidos → sem histórico | `frota/cenario.py::_da_base` | Proposta para validação. Alternativas: dias úteis vs fim de semana antes de "todos os dias"; usar `trechos.tempoBaseMin` em vez de "sem histórico". |
| 4 | Janela | 180 dias, D-1 a D-180, hoje fora | `settings.JANELA_DIAS` | Janela maior aumenta `n` e dilui mudanças recentes de trânsito. |
| 5 | Retenção da raw | TTL 200 dias | `settings.TTL_RAW_DIAS` | Precisa cobrir a janela + margem; também limita até onde o sob demanda alcança. |
| 6 | Validade do salvo sob demanda | período absoluto: 7 dias (1–30); relativo: até o próximo job | `settings.TTL_SALVO_PADRAO_DIAS`, `TTL_SALVO_MAX_DIAS` | Validade maior economiza recálculo; com período que inclui dias recentes, o valor pode ficar congelado até expirar. |
| 7 | Frequência e horário do job | 1×/dia às 03:10 São Paulo (cron UTC `10 6 * * *`) | `settings.JOB_HORA_LOCAL`, `CRON_JOB_UTC`, `atlas-trigger/triggers/jobDiario.json` | Rodar mais vezes não muda as médias (o dia corrente nunca entra); só faz sentido se dados atrasados precisarem aparecer mais cedo. |
| 8 | Instante que define dia e hora | partida do trecho (`observadoEm`) | contrato da ingestão e gerador | Usar chegada ou ponto médio muda a hora de viagens longas; exige reprocessar a raw enquanto ela existir. |
| 9 | Identidade dos pontos | código estável (`BASE-001`, `POSTO-11`) | cadastro mestre | Em produção vem do cadastro de bases/postos, com geofence para associar o GPS ao código. Coordenada bruta nunca é chave. |
| 10 | Tipos de veículo | TOCO, TRUCK, CARRETA, BITREM | `frota/schemas.py::TIPOS_VEICULO` (validator) | Novo tipo exige ampliar o `enum`. Agrupar tipos reduz chaves e aumenta `n`. |
| 11 | Estatística | média simples + desvio-padrão populacional (soma dos quadrados), outliers incluídos | pipeline do job e `frota/cenario.py::_metricas` | `$median`/`$percentile` não se compõem entre horas; alternativas componíveis: média aparada por limites fixos. |

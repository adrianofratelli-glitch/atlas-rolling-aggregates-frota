# Decisões a confirmar com o cliente

A POV escolhe um valor default para cada item abaixo e deixa a escolha **configurável**
(collection `config`) ou isolada num ponto do código. Nenhum desses defaults é uma
recomendação de produção sem a validação do time de operação.

| # | Decisão | Default da POV | Onde mudar | Impacto de mudar |
|---|---|---|---|---|
| 1 | Limites dos turnos | M 06–12, T 12–18, N 18–06 | `config.turnos` (UI: aba Config) | Só a camada 2 é recalculada; raw e buckets não mudam (a hora está no grão do bucket). |
| 2 | Regra da noite | `dia_civil` | `config.regraNoite` | `dia_operacional` faz a madrugada (antes do fim do turno N) contar no dia anterior: sexta 01:00 vira "sexta à noite". Só camada 2. |
| 3 | Instante que define o turno | partida do trecho (`observadoEm`) | gerador e contrato da ingestão | Usar chegada ou ponto médio muda o bucket de viagens que cruzam limites de turno; exige reprocessar a raw (enquanto ela existir). |
| 4 | Identidade dos pontos | código estável (`BASE-001`, `POSTO-0042`) | cadastro mestre | Em produção vem do cadastro mestre de bases/postos e de geofence para associar o GPS ao código. Coordenada bruta nunca é chave. Decisão do cliente. |
| 5 | Tipos de veículo | TOCO, TRUCK, CARRETA, BITREM | `tipos_veiculo` + validator | Novo tipo exige ampliar o `enum` do validator. Agrupar tipos (ex.: leve/pesado) reduz chaves e aumenta n. |
| 6 | Frequência do job | 1×/dia (qualquer hora após 00:00 local) | agendador externo | Mais frequente só faz sentido se o fallback precisar enxergar atrasos mais cedo; o dia corrente nunca entra nas médias. |
| 7 | k de reprocessamento | 3 dias | `config.kReprocessamento` | Maior k absorve mais atrasos sem depender do watermark, ao custo de reler mais raw por run. Atrasos além de k são detectados pelo watermark de `ingeridoEm` e reprocessados mesmo assim. |
| 8 | Amostragem mínima | 5 | `config.minAmostras` (e `?minAmostras=` na API) | Define quando o fallback desce de nível. |
| 9 | Hierarquia de fallback | dow+turno → turno → geral → sem_historico | `frota/consulta.py::escolher_nivel` | Proposta para validação. Alternativas: descer para "mesmo turno, dias úteis vs fim de semana" antes de "turno"; usar o tempo base do trecho (`trechos.tempoBaseMin`) em vez de `sem_historico`. |
| 10 | Retenção da raw | TTL 200 dias | `config.ttlRawDias` + `make up` | Em produção a raw pode ter TTL curto (ex.: 30 dias): os buckets carregam o histórico. Trade-off: depois do TTL não dá para reprocessar com outro grão (ex.: blocos de 15 min) nem trocar a regra 3. |
| 11 | Retenção dos buckets | TTL 190 dias | `config.ttlBucketDias` | Precisa ser ≥ janela + margem; abaixo de 180 a camada 2 perde dias. |
| 12 | Estatística | média simples, outliers incluídos | camada 2 | `$median`/`$percentile` (MongoDB 7.0+) existem, mas **não se compõem** a partir de soma/contagem: exigiriam guardar as amostras (ou um sketch) no bucket, ou recalcular sobre a raw. Alternativas componíveis: média aparada por limites fixos, soma de quadrados para desvio-padrão. |
| 13 | Limpeza da camada 2 | `merge_runid` | `config.modoLimpezaCamada2` | Ver README, seção "Dois modos de limpeza". |
| 14 | Janela | 180 dias, D-1 a D-180 | `config.janelaDias` | Janela maior aumenta n por chave e dilui mudanças recentes de trânsito. |

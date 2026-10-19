# Roteiro de demo (~10 min, 5 passos)

**Na manhã da demo:** abra a UI e clique **Resetar demo** (rodapé do trilho). Sem o
trigger de ingestão implantado, é o reset que gera a raw até o instante do clique e roda o
job do dia; leva menos de 2 minutos no Atlas. Confira no topo o chip **MongoDB Atlas** e
no trilho "base gerada em …" com a data de hoje. Suba com `./start.sh` (ou `make api` +
`make ui`) e abra http://127.0.0.1:5410.

No topo de cada passo, o **mapa do fluxo** acende o trecho daquele passo: use-o para dizer
onde se está ("agora estamos aqui: a raw entra no job"). No passo 3 ele anima a raw indo
para a base e mostra lidas → gravadas; no passo 4 acende o ramo do selo.

| min | Passo | O que fazer | O que dizer |
|---|---|---|---|
| 0–1 | **1 · Dado bruto e schema** | Mostrar a amostra (dias e horas variados) e o schema ao lado. Abrir a gaveta (inclui "Como a ingestão grava"). | Cada trecho percorrido vira uma observação: quando partiu, quanto andou, quanto demorou. Data é BSON Date UTC; o `$jsonSchema` recusa string. Os índices e o porquê de cada um vêm do banco. Em produção quem grava é o rastreio da frota; o `$merge` pelo índice único viagemId+seq não duplica uma viagem. |
| 1–2 | **2 · A regra** | Ler as datas da janela. | Média dos últimos 180 dias, D-1 a D-180: hoje fica fora porque o dia não terminou. A chave é trecho × veículo × dia da semana × hora, no horário de São Paulo. Manhã/tarde/noite são só atalhos de faixa. |
| 2–4 | **3 · Gerar a base** | "Rodar job agora". Percorrer os estágios; parar no `$merge`. Abrir a gaveta. | Um aggregate lê a raw, calcula `$isoDayOfWeek` e `$hour` no fuso, agrupa guardando somas e contagem e grava com `$merge` replace: é a "materialized view". Rodar de novo dá o mesmo resultado. Em produção quem roda é o trigger (passo 5). |
| 4–7 | **4 · Consultar** | Janela padrão: sexta, Tarde; depois seg–sex, Manhã; trocar o tipo. Abrir a gaveta e "Como essa base foi gerada". Escolher um **veículo** (ex.: `VEI-CARRETA-7`), Calcular duas vezes. Trocar para "Datas específicas" (últimas 4 semanas), Calcular. Por fim, um destino "poucos dados" com todos os veículos. | Uma tela só; quem decide de onde vem a média é a API. Janela padrão do tipo inteiro: soma poucos documentos prontos (sexta à tarde = 6); é isto que a aplicação lê quando o ETA online cai. A base é por tipo, não por veículo: com um veículo, ou com outro período, o mesmo cálculo roda na raw na hora e, como "guardar o resultado" vem marcado, o `$merge` grava em `consultas_salvas`; a segunda vez vem "lido do salvo". Janela padrão + veículo vale até o próximo job; datas específicas, pela validade escolhida. O TTL apaga sozinho. No trecho com poucos dados a base amplia e diz como (regra para validar com vocês). |
| 7–9 | **5 · Quando atualiza** | Mostrar agendamento, prévia e histórico. | `$merge` materializa; quem atualiza é o job, não o banco. Em produção: Atlas Scheduled Trigger às 03:10 (código pronto); nesta demo, o botão do passo 3. Amanhã entra o dia de hoje e sai o D-181. |
| 9–10 | **Decisões** | `docs/decisoes-cliente.md`. | Faixas, mínimo de amostras, hierarquia, janela, retenção, validade do salvo, horário do job, partida vs chegada, identidade dos pontos, tipos de veículo, estatística. O modelo é de referência: adaptar ao cadastro real. |

Calcular no passo 4 com "guardar o resultado" marcado (o padrão) grava em `consultas_salvas` do banco da demo; o próximo reset limpa.

## Perguntas prováveis

- **"É uma materialized view?"** É o mesmo resultado: collection materializada + job
  agendado. O refresh é completo sobre a janela, idempotente (`$merge` replace).
- **"E se o job falhar ou rodar duas vezes?"** Rodar de novo produz o mesmo resultado; dois
  runs sobrepostos não apagam um ao outro (a limpeza usa o relógio do servidor). Testado.
- **"Por que hora a hora e não turno?"** Porque assim qualquer faixa ou combinação de dias
  é uma soma; mudar a definição de turno não exige reprocessar.
- **"Funciona no Atlas?"** A demo roda no Atlas (MongoDB 9.0.4); a suíte também passa no
  MongoDB 8.0 local.

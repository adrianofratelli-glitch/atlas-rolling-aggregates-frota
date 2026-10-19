# Roteiro de demo (~10 min, 7 passos)

**Na manhã da demo:** abra a UI e clique **Resetar demo** (rodapé do trilho). Sem o
trigger de ingestão implantado, é o reset que gera a raw até o instante do clique e roda o
job do dia; leva menos de 2 minutos no Atlas. Confira no topo o chip **MongoDB Atlas** e
no trilho "base gerada em …" com a data de hoje. Suba com `./start.sh` (ou `make api` +
`make ui`) e abra http://127.0.0.1:5410.

| min | Passo | O que fazer | O que dizer |
|---|---|---|---|
| 0–1 | **1 · Dado bruto e schema** | Mostrar a amostra (dias e horas variados) e o schema ao lado. Abrir a gaveta. | Cada trecho percorrido vira uma observação: quando partiu, quanto andou, quanto demorou. Data é BSON Date UTC; o `$jsonSchema` recusa string. Os índices e o porquê de cada um vêm do banco. |
| 1–2 | **2 · A regra** | Ler as datas da janela. | Média dos últimos 180 dias, D-1 a D-180: hoje fica fora porque o dia não terminou. A chave é trecho × veículo × dia da semana × hora, no horário de São Paulo. Manhã/tarde/noite são só atalhos de faixa. |
| 2–4 | **3 · Gerar a base** | "Rodar job agora". Percorrer os estágios; parar no `$merge`. Abrir a gaveta. | Um aggregate lê a raw, calcula `$isoDayOfWeek` e `$hour` no fuso, agrupa guardando somas e contagem e grava com `$merge` replace: é a "materialized view". Rodar de novo dá o mesmo resultado. Em produção quem roda é o trigger (passo 6). |
| 4–6 | **4 · Consultar cenários** | Sexta, Tarde; depois seg–sex, Manhã; trocar o veículo. Abrir a gaveta e "Como essa base foi gerada". | Qualquer combinação soma poucos documentos prontos (sexta à tarde = 6). É isto que a aplicação lê quando o ETA online cai. Média ± desvio porque guardamos a soma dos quadrados. |
| 6–7 | **5 · Fora da base** | "Datas específicas" (últimas 4 semanas), Calcular. Marcar "persistir", Calcular duas vezes. | Período fora da janela padrão: o mesmo cálculo direto na raw, na hora. Persistindo, o `$merge` grava em `consultas_salvas` com validade; a segunda vez vem "lido do salvo". O TTL apaga sozinho. |
| 7–8 | **6 · Quando atualiza** | Mostrar agendamento, prévia e histórico. | `$merge` materializa; quem atualiza é o job, não o banco. Em produção: Atlas Scheduled Trigger às 03:10 (código pronto); nesta demo, o botão do passo 3. Amanhã entra o dia de hoje e sai o D-181. |
| 8–9 | **7 · Poucas amostras** | Mostrar o trecho "poucos dados" e o nível usado. | Com menos de 5 amostras a consulta amplia um degrau por vez e diz qual usou. A ordem é uma proposta para validar com vocês. |
| 9–10 | **Decisões** | `docs/decisoes-cliente.md`. | Faixas, mínimo de amostras, hierarquia, janela, retenção, validade do salvo, horário do job, partida vs chegada, identidade dos pontos, tipos de veículo, estatística. O modelo é de referência: adaptar ao cadastro real. |

Persistir no passo 5 grava em `consultas_salvas` do banco da demo; o próximo reset limpa.

## Perguntas prováveis

- **"É uma materialized view?"** É o mesmo resultado: collection materializada + job
  agendado. O refresh é completo sobre a janela, idempotente (`$merge` replace).
- **"E se o job falhar ou rodar duas vezes?"** Rodar de novo produz o mesmo resultado; dois
  runs sobrepostos não apagam um ao outro (a limpeza usa o relógio do servidor). Testado.
- **"Por que hora a hora e não turno?"** Porque assim qualquer faixa ou combinação de dias
  é uma soma; mudar a definição de turno não exige reprocessar.
- **"Funciona no Atlas?"** A demo roda no Atlas (MongoDB 9.0.4); a suíte também passa no
  MongoDB 8.0 local.

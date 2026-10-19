# Fluxos da UI

Fonte: `frontend/src/App.jsx`, `frontend/src/passos/*.jsx`, `frontend/src/comp/*.jsx` e as
rotas de `api/main.py`.

Uma página: trilho à esquerda com os 5 passos (clique livre, `✓` nos visitados), passo
atual no centro, Anterior/Próximo embaixo, passo na URL (`#passo=N`; um passo que não existe, como `#passo=7`, cai no 1). No topo, o chip do
alvo (`MongoDB Atlas` ou `Docker local`). No rodapé do trilho, o frescor da base ("base
gerada em DD/MM HH:MM" sem trigger; "ingestão simulada programada até DD/MM" com trigger) e
o botão **Resetar demo**. Ao carregar: `GET /api/estado` + `GET /api/opcoes`.

| # | Passo | Ação | Rota | Resultado exibido |
|---|---|---|---|---|
| 1 | Dado bruto e schema | abre | `GET /api/raw` | 12 observações do trecho/veículo (data local, dia, hora, km, min); campos e tipos do `$jsonSchema` e índices lidos do banco, cada um com o porquê. |
| 2 | A regra | abre | (`/api/estado`) | janela de 180 dias com as datas de hoje (início entra, fim fica de fora), chave da média, fuso, horário do job. |
| 3 | Gerar a base | "Rodar job agora" | `POST /api/job` | contadores (lidas, gravadas, removidas, tempo), pipeline estágio a estágio com `$merge` destacado (só "Grava o resultado numa collection persistente." e o rótulo "materialized view"; o comentário completo fica na gaveta); antes de rodar, a última execução com status ok e, se a tentativa mais recente falhou, uma nota discreta. |
| 4 | Consultar | origem, destino (só os válidos para a origem, de `/api/opcoes.trechos`), tipo de veículo, veículo ("todos os veículos do tipo" ou um dos 15 de `/api/opcoes.veiculos`), chips de dia, faixa ou atalho Manhã/Tarde/Noite, período ("Janela padrão (últimos 180 dias)", "Datas específicas", "Últimos N dias"). Janela padrão sem veículo: consulta automática (debounce 300 ms, resposta fora de ordem descartada). Qualquer outro caso: caixa "guardar o resultado" **marcada por padrão** + validade 1–30 dias (padrão 7; oculta no período relativo, com "vale até o próximo job") e botão "Calcular" | `POST /api/cenario` | frase "Se a média já estiver pré-calculada, vem da base pronta; senão é calculada agora (e guardada, se marcado)."; média ± desvio, km, amostras, dias somados, horas, docs lidos (em destaque: é a prova de custo), ida e volta ao banco. Selo "Job diário" (base pronta) ou "Sob demanda" com detalhe ("calculado agora na raw (não salvo)", "calculado agora · salvo até DD/MM", "lido do salvo · expira DD/MM"); no sob demanda, docs lidos = documentos da raw no período (antes do filtro de dia/hora); com veículo, docs lidos = `docsExaminados` (o que o índice percorre: trecho × tipo inteiro) e a sub-linha "N do veículo · o índice percorre o trecho × tipo inteiro"; aviso de período parcial fora da retenção; aviso de filtro alterado. Na base, quando `nivel` ≠ `pedido`: o detalhe do selo diz o nível ("poucas amostras: ampliado para …", "sem histórico suficiente, mesmo ampliando") e abaixo entra só a etiqueta "regra a validar com o cliente". |
| 5 | Quando atualiza | abre | `GET /api/job_runs?limite=5`, `GET /api/proximo-job` | horário 03:10 e cron UTC; sem trigger, caixa "Em produção: Atlas Scheduled Trigger…; nesta demo, o job roda pelo botão do passo 3" com atalho para o passo 3; prévia (entra, sai, chaves que somem); últimas execuções com origem. |

Nos passos 1, 3 e 4 a gaveta **"Ver query / chamada executada"** (fechada por padrão)
mostra "Lê de" / "Grava em", o comando mongosh com os operadores destacados, botão copiar
e uma frase por operador; nas respostas da base, também "Como essa base foi gerada" (o
pipeline do job).

**Reset:** diálogo com a data/hora do clique → `POST /api/reset` (202) → a cada ~1 s
`GET /api/reset/status` + `GET /api/estado` (barra com etapa e %); ao terminar recarrega
tudo e remonta o passo. Reset concorrente → 409 com a etapa em andamento.

Estados: backend fora → aviso "rode `make api`" com "Tentar de novo"; 502 do proxy →
"confira `make api`"; base vazia → aviso com botão Resetar demo; sem job ainda → aviso
para rodar o passo 3; durante o reset → 409 em `/api/raw`, `/api/job` e `/api/cenario`, e os
passos mostram o progresso.

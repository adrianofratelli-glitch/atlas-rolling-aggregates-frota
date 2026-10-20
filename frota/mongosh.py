"""Serialização para JSON da API e para texto colável no mongosh."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone

from bson import ObjectId

_IDENT = re.compile(r"^[A-Za-z_$][\w$]*$")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def jsonavel(obj):
    """Converte para tipos JSON: datas em ISO UTC, ObjectId em string."""
    if isinstance(obj, dict):
        return {str(k): jsonavel(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonavel(v) for v in obj]
    if isinstance(obj, datetime):
        return _iso(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, ObjectId):
        return str(obj)
    return obj


def para_mongosh(obj, nivel: int = 0, recuo: str = "  ") -> str:
    """Texto JS para o mongosh: datas como ISODate(...), chaves sem aspas quando possível."""
    pad, pad1 = recuo * nivel, recuo * (nivel + 1)
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        itens = [f"{pad1}{k if _IDENT.match(str(k)) else json.dumps(str(k))}: "
                 f"{para_mongosh(v, nivel + 1, recuo)}" for k, v in obj.items()]
        curto = "{ " + ", ".join(i.strip() for i in itens) + " }"
        return curto if len(curto) <= 88 and "\n" not in curto else "{\n" + ",\n".join(itens) + f"\n{pad}}}"
    if isinstance(obj, (list, tuple)):
        if not obj:
            return "[]"
        itens = [f"{pad1}{para_mongosh(v, nivel + 1, recuo)}" for v in obj]
        curto = "[ " + ", ".join(i.strip() for i in itens) + " ]"
        return curto if len(curto) <= 88 and "\n" not in curto else "[\n" + ",\n".join(itens) + f"\n{pad}]"
    if isinstance(obj, datetime):
        return f'ISODate("{_iso(obj)}")'
    if isinstance(obj, ObjectId):
        return f'ObjectId("{obj}")'
    return json.dumps(obj, ensure_ascii=False)


# Notas curtas ao lado das linhas que costumam travar a leitura (campo → o que significa).
# Casam com a linha inteira, sem recuo; a primeira que casar vale.
_NOTAS = [(re.compile(r), t) for r, t in [
    (r"^observadoEm: \{ \$gte", "o início entra ($gte), o fim fica de fora ($lt)"),
    (r"^dow: \{ \$isoDayOfWeek", "1 = segunda … 7 = domingo, no horário de São Paulo"),
    (r"^hora: \{ \$hour", "0 a 23, no horário de São Paulo"),
    (r"^dow: \{ \$in", "dias da semana escolhidos (1 = segunda … 7 = domingo)"),
    (r"^hora: \{ \$in", "horas cheias escolhidas (8 = das 08:00 às 08:59)"),
    (r"^_id: null", "null = um grupo só: soma tudo que passou pelo filtro"),
    (r"^_id: \{$", "chave do grupo: cada combinação vira um documento de média"),
    (r"^n: \{ \$sum: \"\$n\" \}", "total de observações = soma das contagens que o job já guardou"),
    (r"^n: \{ \$sum: 1 \}", "conta 1 por observação"),
    (r"^somaMin: \{ \$sum", "soma dos tempos de viagem, em minutos"),
    (r"^somaQuadMin: \{ \$sum", "soma de tempo × tempo: é o que permite calcular o desvio padrão depois"),
    (r"^somaKm: \{ \$sum", "soma das distâncias, em km"),
    (r"^docs: \{ \$sum: 1", "quantos documentos prontos entraram na conta"),
    (r"^(somaMin|somaQuadMin|somaKm): \{ \$round", "arredonda para 6 casas (tira ruído de ponto flutuante)"),
    (r"^mediaMin: \{ \$divide", "média do tempo (min) = somaMin ÷ n"),
    (r"^media(Min|Km): \{ \$divide", "média = soma ÷ quantidade de observações"),
    (r"^desvioMin: \{", "desvio padrão = raiz( média dos quadrados − quadrado da média ); $max(0, …) evita raiz de negativo por arredondamento"),
    (r"^(janelaInicio|janelaFim|dataRef|runId): \{ \$literal", "carimbo desta execução, gravado como está"),
    (r"^(atualizadoEm|criadoEm): \"\$\$NOW\"", "$$NOW = o instante em que o documento é gravado"),
    (r"^expiraEm: \{ \$literal", "o índice TTL apaga o documento quando chegar nesta data"),
    (r"^_id: \{ \$literal", "a chave é o identificador do filtro: a mesma consulta cai no mesmo documento"),
    (r"^_id: 0", "0 = não devolve o _id"),
    (r"^into:", "collection de destino"),
    (r"^on:", "campos que dizem quando é \"o mesmo documento\""),
    (r"^whenMatched: \"replace\"", "mesma chave: troca o documento inteiro (nunca soma por cima)"),
    (r"^whenNotMatched: \"insert\"", "chave nova: insere"),
]]


def _anotar(corpo: str) -> str:
    """Põe `// nota` no fim das linhas conhecidas (não mexe nas que já têm comentário)."""
    saida = []
    for linha in corpo.split("\n"):
        nota = next((t for r, t in _NOTAS if r.match(linha.strip())), None)
        saida.append(f"{linha}  // {nota}" if nota and "//" not in linha else linha)
    return "\n".join(saida)


def pipeline_mongosh(colecao: str, comentado: list[dict], operacao: str = "aggregate",
                     rodape: str | None = None) -> str:
    """`db.<colecao>.aggregate([...])` com o comentário de cada estágio acima dele.

    Linhas de campo conhecidas ganham uma nota à direita; `rodape` (opcional) vira
    comentário depois do comando, para explicar o que acontece fora do banco."""
    linhas = [f"db.{colecao}.{operacao}(["]
    for i, e in enumerate(comentado):
        for linha in _quebrar(e["comentario"], 86):
            linhas.append(f"  // {linha}")
        corpo = _anotar(para_mongosh(e["estagio"], 1))
        linhas.append(f"  {corpo.lstrip()}{',' if i < len(comentado) - 1 else ''}")
    linhas.append("])")
    if rodape:
        linhas.append("")
        linhas += [f"// {l}" if l else "//" for l in rodape.split("\n")]
    return "\n".join(linhas)


def _quebrar(texto: str, largura: int) -> list[str]:
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        if len(atual) + len(p) + 1 > largura:
            linhas.append(atual)
            atual = p
        else:
            atual = f"{atual} {p}".strip()
    return linhas + ([atual] if atual else [])

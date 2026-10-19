"""Explicações dos operadores e o bloco "query" que toda resposta da API carrega."""
from __future__ import annotations

from frota.mongosh import pipeline_mongosh

EXPLICACOES: dict[str, str] = {
    "$match": "filtra os documentos, deixando passar só os que atendem à condição.",
    "$set": "acrescenta campos calculados a cada documento sem tirar os que já existem.",
    "$group": "junta os documentos que têm a mesma chave e calcula totais para cada grupo.",
    "$project": "escolhe quais campos saem e calcula os novos.",
    "$merge": "Grava o resultado numa collection persistente.",
    "$isoDayOfWeek": "dia da semana no fuso de São Paulo (1 = segunda … 7 = domingo).",
    "$hour": "hora do dia (0 a 23) no fuso de São Paulo.",
    "$sum": "soma os valores, ou conta os documentos quando o valor é 1.",
    "$round": "arredonda o número para a quantidade de casas indicada.",
    "$divide": "divide o primeiro número pelo segundo.",
    "$in": "confere se o valor está na lista informada.",
    "$or": "aceita o documento se pelo menos uma das condições for verdadeira.",
    "$lt": "menor que (o limite em si fica de fora).",
    "$gte": "maior ou igual a (o limite em si entra).",
    "$gt": "maior que (o limite em si fica de fora).",
    "$multiply": "multiplica os números.",
    "$literal": "usa o valor exatamente como está, sem interpretar como campo.",
}


def _coletar(obj, achados: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.startswith("$") and not k.startswith("$$") and k not in achados:
                achados.append(k)
            _coletar(v, achados)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _coletar(v, achados)


def operadores_usados(pipeline: list[dict]) -> list[str]:
    """Operadores (chaves `$...`) em ordem de aparição, sem repetir. Valores como "$campo" não contam."""
    achados: list[str] = []
    _coletar(pipeline, achados)
    return achados


def bloco_query(colecao: str, comentado: list[dict], le: list[str], grava: list[str],
                operacao: str = "aggregate") -> dict:
    ops = operadores_usados([e["estagio"] for e in comentado])
    return {
        "le": le,
        "grava": grava,
        "operacao": operacao,
        "mongosh": pipeline_mongosh(colecao, comentado, operacao),
        "operadores": [{"op": o, "explicacao": EXPLICACOES.get(o, "")} for o in ops],
    }

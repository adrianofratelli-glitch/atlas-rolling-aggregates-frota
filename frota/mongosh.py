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


def pipeline_mongosh(colecao: str, comentado: list[dict], operacao: str = "aggregate") -> str:
    """`db.<colecao>.aggregate([...])` com o comentário de cada estágio acima dele."""
    linhas = [f"db.{colecao}.{operacao}(["]
    for i, e in enumerate(comentado):
        for linha in _quebrar(e["comentario"], 86):
            linhas.append(f"  // {linha}")
        corpo = para_mongosh(e["estagio"], 1)
        linhas.append(f"  {corpo}{',' if i < len(comentado) - 1 else ''}")
    linhas.append("])")
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

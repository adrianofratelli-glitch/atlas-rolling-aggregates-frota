"""Operadores explicados e bloco de query."""
from __future__ import annotations

from datetime import date, datetime, timezone

from frota.operadores import EXPLICACOES, bloco_query, operadores_usados
from frota.pipelines import comentados, estagios
from frota.cenario import Filtro
from frota.pipelines import cenario as cen_pipe
from frota.pipelines import ingestao as ing_pipe
from frota.pipelines import job as job_pipe

INI = datetime(2026, 4, 22, 3, tzinfo=timezone.utc)
FIM = datetime(2026, 10, 19, 3, tzinfo=timezone.utc)


def _job():
    return job_pipe.pipeline(INI, FIM, date(2026, 10, 19), "r1")


def test_operadores_usados_job():
    ops = operadores_usados(estagios(_job()))
    ordem = ["$match", "$set", "$isoDayOfWeek", "$hour", "$group", "$project", "$merge"]
    assert [o for o in ops if o in ordem] == ordem
    assert len(ops) == len(set(ops))
    assert "$tempoMin" not in ops and "$$NOW" not in ops


def _cenarios():
    f = Filtro(origem="A", destino="B", tipoVeiculo="TRUCK", dias=[1, 5], horaInicio=18,
               horaFim=6, periodo={"tipo": "ultimos", "dias": 30}, persistir=True)
    horas = list(range(18, 24)) + list(range(6))
    return [cen_pipe.base(f, [1, 5], horas),
            cen_pipe.raw(f, INI, FIM, horas, {"_id": "k", "periodo": "relativo", "expiraEm": FIM}),
            cen_pipe.raw(f, INI, FIM, horas, None)]


def test_toda_op_tem_explicacao():
    for p in [_job(), *_cenarios(), ing_pipe.pipeline(FIM)]:
        for op in operadores_usados(estagios(p)):
            assert EXPLICACOES.get(op), op


def test_bloco_query_sem_uri():
    b = bloco_query("trecho_observacoes", comentados(_job()), ["trecho_observacoes"],
                    ["trecho_media_dow_hora"])
    assert b["mongosh"].startswith("db.trecho_observacoes.aggregate([")
    assert b["operacao"] == "aggregate"
    assert {o["op"] for o in b["operadores"]} >= {"$match", "$merge"}
    assert all(o["explicacao"] for o in b["operadores"])
    txt = str(b)
    assert "mongodb" not in txt and "://" not in txt


def test_explicacoes_terminam_com_ponto():
    assert [op for op, txt in EXPLICACOES.items() if not txt.endswith(".")] == []
    assert EXPLICACOES["$isoDayOfWeek"] == ("dia da semana no fuso de São Paulo "
                                            "(1 = segunda … 7 = domingo).")
    assert EXPLICACOES["$merge"] == "Grava o resultado numa collection persistente."

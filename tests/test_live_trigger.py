"""A Function do trigger, executada de verdade no MongoDB (sem App Services).

O deploy do App Services exige chave de Project Owner e escreveria no banco da demo de hora em
hora; aqui a mesma Function versionada (`atlas-trigger/functions/rodarJob.js`) roda pelo
mongosh contra o banco `*_test`, e o resultado tem de ser idêntico ao job do Python.
Também confere que a janela calculada no servidor (`$dateTrunc`/`$dateSubtract` com
`timezone`) bate com `janela.py::janela_padrao` em dias de horário de verão de São Paulo.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from bson import json_util

from backend.frota import job as job_mod
from backend.frota import seed as seed_mod
from backend.frota import settings
from backend.frota.janela import hoje_local, janela_padrao
from backend.frota.pipelines import estagios
from backend.frota.pipelines import job as pl_job

ROOT = Path(__file__).resolve().parent.parent
MONGOSH = shutil.which("mongosh")
UTC = timezone.utc


def _instantes_dst() -> list[datetime]:
    """Viradas do horário de verão de São Paulo (2017–2019) e vizinhança, mais dias comuns."""
    dias = [(2017, 10, 15), (2018, 2, 18), (2018, 11, 4), (2019, 2, 17),  # viradas
            # 180 dias depois de uma virada: o INÍCIO da janela cai no dia sem 00:00
            (2018, 4, 13), (2019, 5, 3),
            (2018, 4, 23), (2019, 8, 16), (2026, 11, 12), (2026, 3, 1)]
    return [datetime(a, m, d, h, mi, tzinfo=UTC)
            for a, m, d in dias for h, mi in ((1, 59), (2, 0), (3, 0), (3, 1), (6, 10), (23, 30))]


def test_janela_no_servidor_igual_ao_python(db):
    """Mesmo com a collection vazia o pipeline devolve 1 documento; o servidor bate com zoneinfo."""
    for agora in _instantes_dst():
        r = list(db.trecho_observacoes.aggregate(estagios(pl_job.janela_no_servidor(agora))))
        assert len(r) == 1, agora
        ref = hoje_local(agora)
        ini, fim = janela_padrao(ref)
        assert (r[0]["inicio"], r[0]["fim"], r[0]["dataRef"]) == (ini, fim, ref.isoformat()), agora
        assert abs((r[0]["t"] - datetime.now(UTC)).total_seconds()) < 300


def _trocar_agora(o, campo: str):
    """O `$project` do builder com `agora` trocado por um campo do documento."""
    if isinstance(o, datetime):
        return campo
    if isinstance(o, dict):
        return {k: _trocar_agora(v, campo) for k, v in o.items()}
    if isinstance(o, list):
        return [_trocar_agora(v, campo) for v in o]
    return o


def test_varredura_2008_2019_igual_ao_python(db):
    """Todo dia de 2008–2019 (anos com horário de verão em SP), 7 horários por dia.

    Usa o mesmo `$project` de `janela_no_servidor`, com `agora` vindo de cada documento de um
    `$documents`: 30.681 instantes em 7 idas ao servidor. Sem o segundo `$dateTrunc`, os dias
    em que o início da janela cai numa virada (ex.: 2018-04-13, 2019-05-03) divergiam.
    """
    proj = _trocar_agora(estagios(pl_job.janela_no_servidor(datetime(2000, 1, 1, tzinfo=UTC)))[2]
                         ["$project"], "$a")
    proj["a"] = 1
    inst, d = [], datetime(2008, 1, 1, tzinfo=UTC)
    while d < datetime(2020, 1, 1, tzinfo=UTC):
        inst += [d.replace(hour=h, minute=m)
                 for h, m in ((1, 59), (2, 0), (2, 59), (3, 0), (3, 1), (6, 10), (23, 30))]
        d += timedelta(days=1)
    divergentes, total = [], 0
    for i in range(0, len(inst), 5000):
        for x in db.aggregate([{"$documents": [{"a": a} for a in inst[i:i + 5000]]},
                               {"$project": proj}]):
            ref = hoje_local(x["a"])
            total += 1
            if (x["inicio"], x["fim"], x["dataRef"]) != (*janela_padrao(ref), ref.isoformat()):
                divergentes.append(x["a"])
    assert total == len(inst) == 30681
    assert divergentes == []


def _sem_run(d: dict) -> dict:
    return {k: v for k, v in d.items() if k not in ("_id", "runId", "atualizadoEm")}


def _base(db) -> dict:
    return {(d["origem"], d["destino"], d["tipoVeiculo"], d["dow"], d["hora"]): _sem_run(d)
            for d in db[pl_job.COLECAO].find({})}


@pytest.mark.skipif(MONGOSH is None, reason="mongosh não instalado")
def test_function_real_igual_ao_job_python(db):
    agora = datetime.now(UTC)
    seed_mod.resetar(db, agora, 1, perfil="teste")
    hoje = hoje_local(agora)
    py = job_mod.rodar_job(db, hoje, "cli")
    esperado = _base(db)
    # uma chave que saiu da janela: a Function tem de removê-la, como o Python
    velho = dict(next(iter(db[pl_job.COLECAO].find({}, {"_id": 0}))))
    velho.update(origem="ZZZ", atualizadoEm=datetime(2020, 1, 1, tzinfo=UTC))
    db[pl_job.COLECAO].insert_one(velho)

    env = {**os.environ, "FROTA_FN_URI": settings.MONGODB_URI, "FROTA_FN_DB": db.name,
           "FROTA_FN": str(ROOT / "atlas-trigger/functions/rodarJob.js")}
    r = subprocess.run([MONGOSH, "--nodb", "--quiet", "--file",
                        str(ROOT / "tests/js/rodar_function_mongosh.js")],
                       env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-500:].replace(settings.MONGODB_URI, "<uri>")
    saida = json_util.loads(r.stdout.strip().splitlines()[-1])

    assert _base(db) == esperado  # mesmas chaves, mesmos n, somas e médias, mesma janela
    run = db.job_runs.find_one({"origem": "trigger"})
    ini, fim = janela_padrao(hoje)
    assert run["status"] == "ok" and run["_id"] == saida["runId"]
    assert (run["dataRef"], run["janelaInicio"], run["janelaFim"]) == (hoje.isoformat(), ini, fim)
    assert run["lidos"] == py["lidos"] and run["gravados"] == py["gravados"] == len(esperado)
    assert run["removidos"] == 1 and db[pl_job.COLECAO].count_documents({"origem": "ZZZ"}) == 0
    assert json.loads(json.dumps(saida["dataRef"])) == hoje.isoformat()

"""Os triggers do Atlas rodam exatamente os pipelines que o Python monta.

O gerador (`scripts/export_pipelines.py`) troca valores por marcadores; aqui conferimos
que substituir os marcadores devolve o mesmo pipeline do builder e que os `.js`
versionados são exatamente o que o gerador produz hoje.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from bson import ObjectId

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import export_pipelines as ex  # noqa: E402

from frota import settings  # noqa: E402
from frota.janela import janela_padrao  # noqa: E402
from frota.mongosh import jsonavel  # noqa: E402
from frota.pipelines import estagios  # noqa: E402
from frota.pipelines import ingestao as pl_ingestao  # noqa: E402
from frota.pipelines import job as pl_job  # noqa: E402

TRIGGER = ROOT / "atlas-trigger"
DATA_REF = date(2026, 10, 22)


def test_template_job_equivale():
    inicio, fim = janela_padrao(DATA_REF)
    run_id = "2026-10-22T06:10:00Z-abcd"
    obtido = ex.substituir(ex.template_job(), {
        "__INICIO__": inicio, "__FIM__": fim,
        "__DATA_REF__": DATA_REF.isoformat(), "__RUN_ID__": run_id})
    assert obtido == estagios(pl_job.pipeline(inicio, fim, DATA_REF, run_id))
    # $$NOW fica literal: quem resolve é o servidor, na hora do aggregate
    assert obtido[3]["$project"]["atualizadoEm"] == "$$NOW"


def test_template_ingestao_equivale():
    agora = datetime(2026, 10, 22, 14, 5, tzinfo=timezone.utc)
    ids = [ObjectId(), ObjectId()]
    assert ex.substituir(ex.template_ingestao(), {"__IDS__": ids}) == \
        estagios(pl_ingestao.pipeline(agora, ids))
    assert ex.substituir(ex.template_filtro_pendentes(), {"__AGORA__": agora}) == \
        pl_ingestao.filtro_pendentes(agora)


def test_substituir_nao_altera_template():
    t = ex.template_job()
    ex.substituir(t, {"__INICIO__": datetime(2026, 1, 1, tzinfo=timezone.utc)})
    assert t == ex.template_job()


def test_js_gerado_atualizado():
    for caminho, conteudo in ex.gerar_functions().items():
        assert (TRIGGER / caminho).read_text() == conteudo, \
            f"{caminho} desatualizado: rode `make pipelines`"


def test_js_contem_template_e_offset():
    js = ex.gerar_functions()
    job = js["functions/rodarJob.js"]
    assert "const OFFSET_SP_HORAS = -3;" in job
    assert json.dumps(ex.template_job(), ensure_ascii=False, indent=2) in job
    assert '"trigger"' in job
    ing = js["functions/ingerirSimulado.js"]
    assert json.dumps(ex.template_ingestao(), ensure_ascii=False, indent=2) in ing
    assert f'const BANCO = "{ex.BANCO}";' in job and f'const BANCO = "{ex.BANCO}";' in ing


def test_cron_bate_com_settings():
    job = json.loads((TRIGGER / "triggers/jobDiario.json").read_text())
    ing = json.loads((TRIGGER / "triggers/ingestaoSimulada.json").read_text())
    assert job["config"]["schedule"] == settings.CRON_JOB_UTC
    assert ing["config"]["schedule"] == settings.CRON_INGESTAO_UTC
    for t, fn in ((job, "rodarJob"), (ing, "ingerirSimulado")):
        assert t["type"] == "SCHEDULED" and t["disabled"] is False
        assert t["config"]["skip_catchup_events"] is True
        assert t["event_processors"]["FUNCTION"]["config"]["function_name"] == fn


def test_sem_ids_versionados():
    hex24 = re.compile(r"\b[0-9a-fA-F]{24}\b")
    arquivos = [p for p in TRIGGER.rglob("*") if p.is_file()]
    assert arquivos
    for p in arquivos:
        texto = p.read_text()
        assert not hex24.search(texto), p
        assert "mongodb.net" not in texto, p
        assert settings._ATLAS == "" or settings._ATLAS not in texto, p
    ds = json.loads((TRIGGER / "data_sources/mongodb-atlas/config.json").read_text())
    # o nome do cluster entra só no deploy (scripts/trigger_deploy.sh, a partir do .env)
    assert ds["config"]["clusterName"] == "${ATLAS_CLUSTER_NAME}"


# ---- as Functions geradas, executadas no node com `context` falso ---------------------

NODE = shutil.which("node")
precisa_node = pytest.mark.skipif(NODE is None, reason="node não instalado")


def _rodar(function: str, instante: str) -> dict:
    r = subprocess.run([NODE, str(ROOT / "tests/js/rodar_function.js"),
                        str(TRIGGER / "functions" / function), instante],
                       capture_output=True, text=True, timeout=30, check=True)
    return json.loads(r.stdout)


@precisa_node
@pytest.mark.parametrize("instante, data_ref", [
    ("2026-10-22T06:10:00Z", date(2026, 10, 22)),   # horário do trigger (03:10 local)
    ("2026-10-22T02:59:00Z", date(2026, 10, 21)),   # 23:59 local do dia anterior
    ("2026-03-01T03:00:00Z", date(2026, 3, 1)),     # 00:00 local; janela atravessa o ano
])
def test_function_job_roda_o_pipeline_do_python(instante, data_ref):
    saida = _rodar("rodarJob.js", instante)
    ops = [(c[0], c[1]) for c in saida["chamadas"]]
    raw, media = f"{ex.BANCO}.trecho_observacoes", f"{ex.BANCO}.{pl_job.COLECAO}"
    assert ops == [("aggregate", raw), ("count", raw), ("aggregate", raw), ("count", media),
                   ("deleteMany", media), ("insertOne", f"{ex.BANCO}.job_runs")]
    run = saida["chamadas"][-1][2]
    inicio, fim = janela_padrao(data_ref)
    servidor = datetime.fromisoformat(instante.replace("Z", "+00:00")) + timedelta(seconds=1)
    assert re.fullmatch(re.escape(servidor.strftime("%Y-%m-%dT%H:%M:%SZ")) + r"-[0-9a-f]{4}",
                        run["runId"])
    esperado = jsonavel(estagios(pl_job.pipeline(inicio, fim, data_ref, run["runId"])))
    assert saida["chamadas"][2][2] == esperado
    assert saida["chamadas"][1][2] == esperado[0]["$match"]
    assert saida["chamadas"][4][2] == {"atualizadoEm": {"$lt": jsonavel(servidor)}}
    assert {k: run[k] for k in ("_id", "origem", "dataRef", "status", "janelaInicio",
                                "janelaFim", "lidos", "gravados", "removidos")} == {
        "_id": run["runId"], "origem": "trigger", "dataRef": data_ref.isoformat(),
        "status": "ok", "janelaInicio": jsonavel(inicio), "janelaFim": jsonavel(fim),
        "lidos": 7, "gravados": 7, "removidos": 2}
    assert run["iniciadoEm"] == jsonavel(servidor)


@precisa_node
def test_function_ingestao_move_por_ids():
    instante = "2026-10-22T14:05:00Z"
    agora = datetime(2026, 10, 22, 14, 5, tzinfo=timezone.utc)
    saida = _rodar("ingerirSimulado.js", instante)
    fila = f"{ex.BANCO}.{pl_ingestao.ORIGEM}"
    c = saida["chamadas"]
    assert [(x[0], x[1]) for x in c] == [("find", fila), ("aggregate", fila),
                                         ("deleteMany", fila), ("count", fila)]
    assert c[0][2] == jsonavel(pl_ingestao.filtro_pendentes(agora))
    assert c[1][2] == estagios(pl_ingestao.pipeline(agora, ["a", "b"]))
    assert c[2][2] == {"_id": {"$in": ["a", "b"]}}
    assert saida["r"] == {"movidos": 2, "restantes": 7}

"""Camada 2: buckets → média histórica (dow × turno) e as regras de janela."""
from __future__ import annotations

import pytest

from frota.job import materializar
from tests.conftest import set_config
from tests.fixtures.dataset import ASOF, sp

A = {"origem": "BASE-001", "destino": "POSTO-0042", "tipoVeiculo": "BITREM"}
NEG = {"_id": 0, "atualizadoEm": 0, "runId": 0}


def media(db, **chave):
    return db.trecho_media_historica.find_one({**A, **chave}, NEG)


def chaves(db, filtro=A):
    return sorted((d["dow"], d["turno"], d["n"])
                  for d in db.trecho_media_historica.find(filtro))


def test_sexta_a_noite_combina_as_tres_sextas_dia_civil(db):
    materializar(db, ASOF)
    m = media(db, dow=6, turno="N")
    assert (m["n"], m["somaMin"], m["mediaMin"], m["somaKm"], m["mediaKm"]) == \
        (3, 168, 56.0, 120, 40.0)
    assert media(db, dow=7, turno="N")["mediaMin"] == 70.0
    assert m["janelaInicio"] == sp(2026, 4, 19) and m["janelaFim"] == sp(2026, 10, 16)
    assert m["asOf"] == ASOF


def test_regra_noite_dia_operacional(db):
    set_config(db, regraNoite="dia_operacional")
    materializar(db, ASOF)
    m = media(db, dow=6, turno="N")
    assert (m["n"], m["somaMin"], m["mediaMin"], m["somaKm"], m["mediaKm"]) == \
        (4, 238, 59.5, 162, 40.5)
    # Nota sobre o contrato 14.1: ele diz que {dow: 7, N} deixa de existir, mas a obs 6
    # (dom 19/04 00:00, hora 0 < 6) também desce um dia: vira sábado. Então {dow: 7, N}
    # existe e contém só a obs 6 (30 min) — a obs 4 (70 min) saiu dele — e {dow: 1, N}
    # é que deixa de existir.
    m7 = media(db, dow=7, turno="N")
    assert (m7["n"], m7["somaMin"]) == (1, 30)
    assert media(db, dow=1, turno="N") is None


def test_bordas_da_janela(db):
    """Entram: 00:00:00.000 de D-180 e 23:59:59.999 de D-1. Saem: D-181 e hoje 00:00."""
    materializar(db, ASOF)
    assert chaves(db) == [(1, "N", 1), (5, "N", 1), (6, "N", 3), (7, "N", 1)]
    assert media(db, dow=1, turno="N")["somaMin"] == 30      # obs 6, borda inicial
    assert media(db, dow=5, turno="N")["somaMin"] == 45      # obs 8, borda final
    # nenhum agregado contém 999 (obs 5, 7, 9)
    assert db.trecho_media_historica.count_documents({"somaMin": {"$gte": 999}}) == 0


def test_separa_turno_e_tipo_de_veiculo(db):
    materializar(db, ASOF)
    b = {"origem": "BASE-001", "destino": "POSTO-0007"}
    car = {(d["dow"], d["turno"]): d["mediaMin"]
           for d in db.trecho_media_historica.find({**b, "tipoVeiculo": "CARRETA"})}
    toco = {(d["dow"], d["turno"]): d["mediaMin"]
            for d in db.trecho_media_historica.find({**b, "tipoVeiculo": "TOCO"})}
    assert car == {(3, "M"): 30.0, (3, "T"): 25.0, (3, "N"): 18.0}
    assert toco == {(3, "M"): 22.0, (2, "M"): 24.0}


def test_idempotente_byte_a_byte(db):
    materializar(db, ASOF)
    antes = list(db.trecho_media_historica.find({}, NEG).sort([("destino", 1), ("tipoVeiculo", 1), ("dow", 1), ("turno", 1)]))
    materializar(db, ASOF)
    depois = list(db.trecho_media_historica.find({}, NEG).sort([("destino", 1), ("tipoVeiculo", 1), ("dow", 1), ("turno", 1)]))
    assert antes == depois


@pytest.mark.parametrize("modo", ["merge_runid", "out"])
def test_avanco_de_janela_remove_obsoletos(db, modo):
    """asOf 17/10: obs 6 (19/04) sai; o dia que era hoje (16/10) passa a contar.

    Nota sobre o contrato 14.1: ele espera dow 6/N com n = 4 e somaMin = 1167, mas
    esqueceu a obs 9 (sex 16/10 00:00:00.000, 999), que também passa a ser D-1 e cai
    em dow 6 (civil) / turno N (hora 0). O valor correto é n = 5, somaMin = 2166.
    """
    set_config(db, modoLimpezaCamada2=modo)
    materializar(db, ASOF)
    assert media(db, dow=1, turno="N") is not None
    run = materializar(db, "2026-10-17")
    assert media(db, dow=1, turno="N") is None
    m = media(db, dow=6, turno="N")
    assert (m["n"], m["somaMin"]) == (5, 50 + 56 + 62 + 999 + 999)
    c2 = run["stats"]["camada2"]
    assert c2["modo"] == modo and c2["removidos"] == 1
    assert {"dow": 1, "turno": "N", **A} in c2["removidosAmostra"]
    # validator e índices sobrevivem ao $out
    opts = db.command("listCollections", filter={"name": "trecho_media_historica"})
    assert "$jsonSchema" in opts["cursor"]["firstBatch"][0]["options"]["validator"]
    nomes = {i["name"] for i in db.trecho_media_historica.list_indexes()}
    assert "chave_media_unica" in nomes


def test_mudar_turno_so_reprocessa_camada2(db):
    materializar(db, ASOF)
    buckets_antes = list(db.trecho_bucket_diario.find({}, {"_id": 1, "runId": 1}))
    set_config(db, turnos=[{"codigo": "M", "inicioHora": 5, "fimHora": 12},
                           {"codigo": "T", "inicioHora": 12, "fimHora": 20},
                           {"codigo": "N", "inicioHora": 20, "fimHora": 5}])
    run = materializar(db, ASOF, camada="2")
    assert "camada1" not in run["stats"]
    assert list(db.trecho_bucket_diario.find({}, {"_id": 1, "runId": 1})) == buckets_antes
    # 20:00 continua N; 14:00 da carreta continua T; nada some, só reclassifica
    assert media(db, dow=6, turno="N")["n"] == 3
    assert media(db, dow=6, turno="N")["configVersao"] == run["configVersao"]


def test_turnos_invalidos_sao_recusados(db):
    with pytest.raises(ValueError):
        set_config(db, turnos=[{"codigo": "M", "inicioHora": 6, "fimHora": 12}])

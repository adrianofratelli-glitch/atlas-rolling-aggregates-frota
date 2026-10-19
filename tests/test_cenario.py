"""Cenários: base pronta na janela padrão, raw sob demanda (persistível) e ampliação."""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

import pytest

from frota import cenario
from frota import seed as seed_mod
from frota.janela import hoje_local, horas_da_faixa, janela_padrao, proximo_job
from frota.schemas import VALIDATORS
from frota.settings import MIN_AMOSTRAS

# Instante "real" (hora cheia): o TTL de `consultas_salvas` usa o relógio do servidor, então
# um `agora` fixo no passado faria o monitor apagar o doc salvo no meio do teste.
AGORA = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
HOJE = hoje_local(AGORA)
BASE = "trecho_media_dow_hora"
FALSO = {"origem": "FAKE-O", "destino": "FAKE-D", "tipoVeiculo": "TRUCK"}


@pytest.fixture(scope="module")
def semeado(db_sessao):
    for nome in VALIDATORS:
        db_sessao[nome].delete_many({})
    seed_mod.resetar(db_sessao, AGORA, 1, perfil="teste")
    return db_sessao


@pytest.fixture
def db(semeado):
    """Base semeada uma vez por módulo; cada teste começa sem salvos e sem a rota falsa."""
    semeado.consultas_salvas.delete_many({})
    semeado[BASE].delete_many({"origem": FALSO["origem"]})
    yield semeado
    semeado[BASE].delete_many({"origem": FALSO["origem"]})


def _regulares(db):
    return [t for t in db.trechos.find() if not t.get("esparso")]


def _filtro(t=None, dias=(1, 2, 3, 4, 5, 6, 7), hi=7, hf=10, periodo=None, **kw):
    o = {"origem": t["origem"], "destino": t["destino"], "tipoVeiculo": "TRUCK"} if t else FALSO
    return cenario.Filtro(**{**o, **kw.pop("rota", {})}, dias=list(dias), horaInicio=hi,
                          horaFim=hf, periodo=periodo or {"tipo": "padrao"}, **kw)


def _janela_em_datas():
    return {"tipo": "datas", "de": (HOJE - timedelta(days=180)).isoformat(),
            "ate": (HOJE - timedelta(days=1)).isoformat()}


def _base_falsa(db, celulas: dict[tuple[int, int], int]):
    """Insere docs controlados na base: (dow, hora) → n, cada amostra valendo 10 min / 5 km."""
    ini, fim = janela_padrao(HOJE)
    db[BASE].insert_many([{
        **FALSO, "dow": dow, "hora": hora, "n": n, "somaMin": 10.0 * n,
        "somaQuadMin": 100.0 * n, "somaKm": 5.0 * n, "mediaMin": 10.0, "mediaKm": 5.0,
        "janelaInicio": ini, "janelaFim": fim, "dataRef": HOJE.isoformat(), "runId": "t",
        "atualizadoEm": AGORA} for (dow, hora), n in celulas.items()])


def test_equivalencia_base_vs_raw(db):
    rng = random.Random(1)
    trechos = _regulares(db)
    for _ in range(20):
        t = rng.choice(trechos)
        tipo = rng.choice(["TRUCK", "CARRETA"])
        dias = sorted(rng.sample(range(1, 8), rng.randint(1, 7)))
        hi = rng.randrange(24)
        hf = rng.choice([h for h in range(25) if h != hi])
        kw = {"rota": {"tipoVeiculo": tipo}}
        b = cenario.consultar(db, _filtro(t, dias, hi, hf, **kw), AGORA)
        r = cenario.consultar(db, _filtro(t, dias, hi, hf, periodo=_janela_em_datas(), **kw), AGORA)
        assert b["selo"] == "job_diario" and b["nivel"] == "pedido"
        assert r["selo"] == "sob_demanda"
        rb, rr = b["resultado"], r["resultado"]
        assert rb["n"] == rr["n"] > 0
        assert abs(rb["mediaMin"] - rr["mediaMin"]) < 1e-6
        assert abs(rb["mediaKm"] - rr["mediaKm"]) < 1e-6
        assert abs(rb["desvioMin"] - rr["desvioMin"]) < 1e-6


def test_faixa_noite_cruza_meia_noite(db):
    t = _regulares(db)[0]
    r = cenario.consultar(db, _filtro(t, [3], 18, 6), AGORA)
    horas = list(range(18, 24)) + list(range(0, 6))
    assert r["resultado"]["horas"] == horas
    esperado = sum(d["n"] for d in db[BASE].find(
        {"origem": t["origem"], "destino": t["destino"], "tipoVeiculo": "TRUCK", "dow": 3,
         "hora": {"$in": horas}}))
    assert r["resultado"]["n"] == esperado and r["resultado"]["docsLidos"] == 12


def test_amplia_todos_os_dias(db):
    _base_falsa(db, {(1, 8): 2, (2, 8): 2, (3, 8): 2})
    r = cenario.consultar(db, _filtro(dias=[1], hi=8, hf=9), AGORA)
    assert r["nivel"] == "todos_os_dias"
    assert r["resultado"]["n"] == 6 and r["resultado"]["diasSomados"] == list(range(1, 8))
    assert "todos os dias" in r["detalhe"]


def test_amplia_dia_inteiro(db):
    _base_falsa(db, {(1, 8): 2, (1, 20): 4})
    r = cenario.consultar(db, _filtro(dias=[1], hi=8, hf=9), AGORA)
    assert r["nivel"] == "dia_inteiro"
    assert r["resultado"]["n"] == 6 and r["resultado"]["horas"] == list(range(24))
    assert "dia inteiro" in r["detalhe"]


def test_sem_historico(db):
    _base_falsa(db, {(1, 8): 1, (2, 3): 1})
    r = cenario.consultar(db, _filtro(dias=[1], hi=8, hf=9), AGORA)
    assert r["nivel"] == "sem_historico" and r["resultado"] is None
    assert r["aviso"]


def test_trecho_esparso_amplia_ou_sem_historico(db):
    t = db.trechos.find_one({"esparso": True})
    r = cenario.consultar(db, _filtro(t, [1], 8, 9), AGORA)
    assert r["nivel"] in ("todos_os_dias", "dia_inteiro", "sem_historico")
    if r["resultado"]:
        assert r["resultado"]["n"] >= MIN_AMOSTRAS


def test_sob_demanda_nao_salva_por_padrao(db):
    t = _regulares(db)[0]
    r = cenario.consultar(db, _filtro(t, periodo={"tipo": "ultimos", "dias": 30}), AGORA)
    assert r["selo"] == "sob_demanda" and r["resultado"]["n"] > 0
    assert r["detalhe"] == "calculado agora na raw (não salvo)"
    assert r["expiraEm"] is None and r["geradoPor"] is None
    assert db.consultas_salvas.count_documents({}) == 0


def test_persistir_e_ler_do_salvo(db):
    t = _regulares(db)[0]
    per = {"tipo": "datas", "de": (HOJE - timedelta(days=20)).isoformat(),
           "ate": (HOJE - timedelta(days=5)).isoformat()}
    f = _filtro(t, periodo=per, persistir=True, ttlDias=3)
    r1 = cenario.consultar(db, f, AGORA)
    exp = AGORA + timedelta(days=3)
    assert r1["expiraEm"] == exp
    assert r1["detalhe"] == f"calculado agora · salvo até {exp.astimezone(cenario._TZ):%d/%m}"
    assert db.consultas_salvas.count_documents({}) == 1
    salvo = db.consultas_salvas.find_one()
    assert salvo["_id"] == f.chave(AGORA) and salvo["periodo"] == "absoluto"
    r2 = cenario.consultar(db, f, AGORA)
    assert r2["detalhe"].startswith("lido do salvo")
    assert r2["query"]["le"] == ["consultas_salvas"] and r2["query"]["grava"] == []
    assert "db.consultas_salvas.findOne(" in r2["query"]["mongosh"]
    assert all(o["explicacao"] for o in r2["query"]["operadores"])
    assert r2["resultado"]["n"] == r1["resultado"]["n"]
    assert r2["resultado"]["mediaMin"] == pytest.approx(r1["resultado"]["mediaMin"])
    assert db.consultas_salvas.count_documents({}) == 1


def test_salvo_expirado_nao_servido(db):
    t = _regulares(db)[0]
    f = _filtro(t, periodo={"tipo": "ultimos", "dias": 10}, persistir=True)
    cenario.consultar(db, f, AGORA)
    db.consultas_salvas.update_one({}, {"$set": {"n": 1, "expiraEm": AGORA - timedelta(minutes=1)}})
    r = cenario.consultar(db, f, AGORA)
    assert r["detalhe"].startswith("calculado agora")
    assert r["resultado"]["n"] > 1


def test_relativo_expira_no_proximo_job(db):
    t = _regulares(db)[0]
    r = cenario.consultar(db, _filtro(t, periodo={"tipo": "ultimos", "dias": 30},
                                      persistir=True, ttlDias=20), AGORA)
    assert r["expiraEm"] == proximo_job(AGORA)
    assert db.consultas_salvas.find_one()["periodo"] == "relativo"


def test_ttl_fora_do_limite(db):
    t = _regulares(db)[0]
    for ttl in (0, 31):
        with pytest.raises(ValueError):
            _filtro(t, periodo={"tipo": "ultimos", "dias": 30}, persistir=True,
                    ttlDias=ttl).validar()


def test_periodo_sem_raw(db):
    t = _regulares(db)[0]
    futuro = (HOJE + timedelta(days=2)).isoformat()
    for per in ({"tipo": "datas", "de": "2020-01-01", "ate": "2020-01-31"},
                {"tipo": "datas", "de": futuro, "ate": futuro}):
        r = cenario.consultar(db, _filtro(t, periodo=per, persistir=True), AGORA)
        assert r["aviso"] == "sem dados brutos para esse período"
        assert r["resultado"] is None
    assert db.consultas_salvas.count_documents({}) == 0


def test_periodo_parcial_calcula(db):
    t = _regulares(db)[0]
    per = {"tipo": "datas", "de": "2020-01-01", "ate": (HOJE - timedelta(days=1)).isoformat()}
    r = cenario.consultar(db, _filtro(t, periodo=per), AGORA)
    assert r["aviso"] is None and r["resultado"]["n"] > 0


def test_filtro_sem_dias(db):
    t = _regulares(db)[0]
    with pytest.raises(ValueError):
        _filtro(t, dias=[]).validar()
    with pytest.raises(ValueError):
        cenario.consultar(db, _filtro(t, dias=[]), AGORA)
    with pytest.raises(ValueError):
        _filtro(t, dias=[8]).validar()


def test_chave_estavel():
    a = _filtro(dias=[3, 1], periodo={"tipo": "ultimos", "dias": 30})
    b = _filtro(dias=[1, 3], periodo={"tipo": "ultimos", "dias": 30}, persistir=True)
    assert a.chave(AGORA) == b.chave(AGORA)
    assert a.chave(AGORA) != a.chave(AGORA + timedelta(days=1))
    c = _filtro(dias=[1, 3], periodo={"tipo": "datas", "de": "2026-09-01", "ate": "2026-09-10"})
    assert c.chave(AGORA) == c.chave(AGORA + timedelta(days=1))


def test_query_bloco_cita_colecoes(db):
    t = _regulares(db)[0]
    b = cenario.consultar(db, _filtro(t), AGORA)
    assert b["query"]["le"] == [BASE] and b["query"]["grava"] == []
    assert b["query"]["mongosh"].startswith(f"db.{BASE}.aggregate([")
    assert b["geradoPor"]["le"] == ["trecho_observacoes"] and b["geradoPor"]["grava"] == [BASE]
    p = cenario.consultar(db, _filtro(t, periodo={"tipo": "ultimos", "dias": 30},
                                      persistir=True), AGORA)
    assert p["query"]["le"] == ["trecho_observacoes"]
    assert p["query"]["grava"] == ["consultas_salvas"]
    assert "$merge" in p["query"]["mongosh"]
    assert "$merge" in {o["op"] for o in p["query"]["operadores"]}
    n = cenario.consultar(db, _filtro(t, periodo={"tipo": "ultimos", "dias": 29}), AGORA)
    assert n["query"]["grava"] == [] and "$merge" not in n["query"]["mongosh"]

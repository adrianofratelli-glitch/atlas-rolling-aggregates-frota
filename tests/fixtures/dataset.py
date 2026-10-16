"""Dataset determinístico montado à mão (contrato da seção 14.1).

Horários escritos em hora local de São Paulo (UTC−3, sem horário de verão desde 2019)
e convertidos para UTC aqui; o banco só vê BSON Date UTC. Valores 999/99 marcam
observações que **não podem** entrar em nenhum agregado com asOf = 2026-10-16.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SP = ZoneInfo("America/Sao_Paulo")
UTC = timezone.utc
ASOF = "2026-10-16"  # sexta-feira


def sp(ano, mes, dia, h=0, m=0, s=0, ms=0) -> datetime:
    return datetime(ano, mes, dia, h, m, s, ms * 1000, tzinfo=SP).astimezone(UTC)


PONTOS = [
    {"_id": "BASE-001", "tipo": "base", "nome": "Base Paulínia", "cidade": "Paulínia", "uf": "SP",
     "location": {"type": "Point", "coordinates": [-47.15, -22.76]}},
    {"_id": "POSTO-0042", "tipo": "posto", "nome": "Posto 0042", "cidade": "Campinas", "uf": "SP",
     "location": {"type": "Point", "coordinates": [-47.06, -22.90]}},
    {"_id": "POSTO-0007", "tipo": "posto", "nome": "Posto 0007", "cidade": "Sumaré", "uf": "SP",
     "location": {"type": "Point", "coordinates": [-47.27, -22.82]}},
    {"_id": "POSTO-9999", "tipo": "posto", "nome": "Posto 9999", "cidade": "Hortolândia", "uf": "SP",
     "location": {"type": "Point", "coordinates": [-47.22, -22.86]}},
]
TIPOS = [
    {"_id": "TOCO", "descricao": "Toco", "capacidadeM3": 6, "fatorTempo": 1.00},
    {"_id": "TRUCK", "descricao": "Truck", "capacidadeM3": 14, "fatorTempo": 1.05},
    {"_id": "CARRETA", "descricao": "Carreta", "capacidadeM3": 30, "fatorTempo": 1.10},
    {"_id": "BITREM", "descricao": "Bitrem", "capacidadeM3": 45, "fatorTempo": 1.18},
]
VEICULOS = [
    {"_id": "VEI-0001", "placa": "ABC1D23", "tipoVeiculo": "BITREM", "baseId": "BASE-001", "ativo": True},
    {"_id": "VEI-0002", "placa": "DEF4G56", "tipoVeiculo": "CARRETA", "baseId": "BASE-001", "ativo": True},
    {"_id": "VEI-0003", "placa": "HIJ7K89", "tipoVeiculo": "TOCO", "baseId": "BASE-001", "ativo": True},
]
TRECHOS = [
    {"_id": "BASE-001|POSTO-0042", "origem": "BASE-001", "destino": "POSTO-0042",
     "distanciaBaseKm": 38.4, "tempoBaseMin": 41.0},
    {"_id": "BASE-001|POSTO-0007", "origem": "BASE-001", "destino": "POSTO-0007",
     "distanciaBaseKm": 20.0, "tempoBaseMin": 22.0},
    {"_id": "BASE-001|POSTO-9999", "origem": "BASE-001", "destino": "POSTO-9999",
     "distanciaBaseKm": 15.0, "tempoBaseMin": 18.0},  # malha conhecida, sem histórico
]

VEI = {"BITREM": "VEI-0001", "CARRETA": "VEI-0002", "TOCO": "VEI-0003"}


def obs(rotulo, origem, destino, tipo, quando, tempo, km, ingerido=None):
    return {"origem": origem, "destino": destino, "tipoVeiculo": tipo, "veiculoId": VEI[tipo],
            "viagemId": f"VIA-FIX-{rotulo}", "seq": 1, "observadoEm": quando,
            "ingeridoEm": ingerido or quando + timedelta(minutes=30),
            "distanciaKm": float(km), "tempoMin": float(tempo)}


A = ("BASE-001", "POSTO-0042", "BITREM")
B = ("BASE-001", "POSTO-0007")

# Tabela 14.1 — trecho A, BITREM
OBS_A = {
    1: obs("A1", *A, sp(2026, 9, 25, 20), 50, 39),                 # sex: dow 6 N
    2: obs("A2", *A, sp(2026, 10, 2, 20), 56, 40),                 # sex: dow 6 N
    3: obs("A3", *A, sp(2026, 10, 9, 20), 62, 41),                 # sex: dow 6 N
    4: obs("A4", *A, sp(2026, 10, 10, 1), 70, 42),                 # sáb 01:00: civil 7 · operacional 6
    5: obs("A5", *A, sp(2026, 10, 16, 20), 999, 99),               # hoje → sai
    6: obs("A6", *A, sp(2026, 4, 19, 0, 0, 0, 0), 30, 38),         # D-180 00:00:00.000 → entra
    7: obs("A7", *A, sp(2026, 4, 18, 23, 59, 59, 999), 999, 99),   # D-181 23:59:59.999 → sai
    8: obs("A8", *A, sp(2026, 10, 15, 23, 59, 59, 999), 45, 39),   # D-1 23:59:59.999 → entra
    9: obs("A9", *A, sp(2026, 10, 16, 0, 0, 0, 0), 999, 99),       # hoje 00:00:00.000 → sai
}

# Trecho B — mesmo trecho em manhã/tarde/noite e dois tipos de veículo (ter 13/10 = dow 3)
OBS_B = [
    obs("B1", *B, "CARRETA", sp(2026, 10, 13, 7, 30), 30, 20),     # M
    obs("B2", *B, "CARRETA", sp(2026, 10, 13, 14, 0), 25, 20),     # T
    obs("B3", *B, "CARRETA", sp(2026, 10, 13, 23, 30), 18, 20),    # N; em UTC já é 14/10 02:30
    obs("B4", *B, "TOCO", sp(2026, 10, 13, 7, 45), 22, 20),        # M, dow 3
    obs("B5", *B, "TOCO", sp(2026, 10, 12, 8, 15), 24, 20),        # M, dow 2 (segunda)
]

# Atrasado de D-2 (qua 14/10 08:00) — inserido só depois do primeiro job
ATRASADO_D2 = obs("LATE-D2", *A, sp(2026, 10, 14, 8), 40, 39)


def observacoes() -> list[dict]:
    return [dict(o) for o in OBS_A.values()] + [dict(o) for o in OBS_B]


def carregar(db) -> None:
    from frota.bootstrap import limpar_dados
    limpar_dados(db)
    db.pontos.insert_many(PONTOS)
    db.tipos_veiculo.insert_many(TIPOS)
    db.veiculos.insert_many(VEICULOS)
    db.trechos.insert_many(TRECHOS)
    db.trecho_observacoes.insert_many(observacoes())

"""Gerador sintético determinístico: malha e observações de trechos.

Os perfis são tamanhos de laboratório. A forma do tempo de deslocamento:

    tempoMin = tempoBaseMin × fatorHora × fatorDow × fatorTipo × ruído log-normal(σ 0,12)

com picos 7–9h e 17–19h, madrugada mais rápida, segunda de manhã e sexta à tarde mais
lentas e ~1% de outliers (parada longa) que não são filtrados.

Determinismo: o resultado depende de `seed` + `perfil`; `agora` só desloca o calendário
(o sorteio de cada dia usa o deslocamento em relação a hoje, não a data absoluta).
A contagem de observações por (trecho regular × tipo × dia × hora) é determinística pelo
peso da hora, o que garante cobertura de toda célula dow×hora na janela de 180 dias.
O veículo (`VEI-<TIPO>-1..N`) é escolhido em rodízio pela sequência do dia deslocada pelo
dia: muda só a distribuição entre veículos, não o volume nem o sorteio dos tempos.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from .janela import hoje_local, inicio_dia
from .settings import DIAS_SIMULADOS, TTL_RAW_DIAS

BASES = [  # (cidade, lon, lat)
    ("Paulínia", -47.15, -22.76), ("Guarulhos", -46.53, -23.45),
    ("Ribeirão Preto", -47.81, -21.18), ("São José dos Campos", -45.89, -23.22),
]
FATOR_TIPO = {"TOCO": 1.00, "TRUCK": 1.05, "CARRETA": 1.10, "BITREM": 1.18}
# malha "completa": toda base atende todo posto (N × N) e cada posto volta à sua base; viagem
# longa (entre regiões) só com os tipos pesados. "basica": poucos trechos, para os testes.
TIPOS_PESADOS = ["CARRETA", "BITREM"]
KM_VIAGEM_LONGA = 120
PERFIS = {
    "demo": {"bases": 4, "tipos": ["TOCO", "TRUCK", "CARRETA", "BITREM"], "dias": TTL_RAW_DIAS,
             "veiculos": 15, "malha": "completa", "peso_pico": 1},
    "teste": {"bases": 1, "tipos": ["TRUCK", "CARRETA"], "dias": 40, "veiculos": 3,
              "malha": "basica", "peso_pico": 3},
}
P_ESPARSO = 0.03
SIGMA_RUIDO = 0.12
P_OUTLIER = 0.01


def peso_hora(h: int, pico: int = 3) -> int:
    """Observações por trecho × tipo × hora: `pico` nos picos, 1 nos demais (mín. 1 = cobertura)."""
    return pico if h in (7, 8, 9, 17, 18, 19) else 1


def fator_hora(h: int) -> float:
    if h < 5:
        return 0.85
    if h < 7:
        return 0.95
    if h < 10:
        return 1.35
    if h < 17:
        return 1.10
    if h < 20:
        return 1.40
    return 0.95


def fator_dow(dow: int, hora: int) -> float:
    """dow ISO (1 = segunda). Segunda de manhã e sexta à tarde pesam mais."""
    f = {6: 0.95, 7: 0.85}.get(dow, 1.0)
    if dow == 1 and 5 <= hora < 12:
        f = 1.12
    if dow == 5 and 12 <= hora < 20:
        f = 1.18
    return f


def _haversine_km(a, b) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + \
        math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _malha(perfil: str, seed: int) -> tuple[list[dict], list[dict]]:
    p = PERFIS[perfil]
    rng = random.Random(f"{seed}-{perfil}-malha")
    pontos, coords, postos = [], {}, {}  # postos: base -> [posto, ...]
    for i, (cidade, lon, lat) in enumerate(BASES[:p["bases"]], start=1):
        bid = f"BASE-{i:03d}"
        coords[bid] = (lon, lat)
        pontos.append({"_id": bid, "tipo": "base", "nome": f"Base {cidade}", "cidade": cidade,
                       "uf": "SP", "location": {"type": "Point", "coordinates": [lon, lat]}})
        postos[bid] = []
        for j in range(1, 4):
            pid = f"POSTO-{i}{j}"
            c = (round(lon + rng.gauss(0, 0.2), 4), round(lat + rng.gauss(0, 0.16), 4))
            coords[pid] = c
            postos[bid].append(pid)
            pontos.append({"_id": pid, "tipo": "posto", "nome": f"Posto {i}{j}",
                           "cidade": cidade, "uf": "SP",
                           "location": {"type": "Point", "coordinates": list(c)}})
    pares = _pares(p, postos)  # (origem, destino, esparso)
    trechos = []
    for o, d, esparso in pares:
        reta = _haversine_km(coords[o], coords[d])
        km = max(round(reta * random.Random(f"{seed}-{o}-{d}").uniform(1.2, 1.45), 1), 1.5)
        vel = 35 if km < 15 else 55 if km < 60 else 70
        tipos = p["tipos"] if km < KM_VIAGEM_LONGA else [t for t in p["tipos"] if t in TIPOS_PESADOS]
        trechos.append({"_id": f"{o}|{d}", "origem": o, "destino": d, "distanciaBaseKm": km,
                        "tempoBaseMin": round(km / vel * 60, 1), "esparso": esparso,
                        "tiposVeiculo": tipos})
    return pontos, trechos


def _pares(p: dict, postos: dict[str, list[str]]) -> list[tuple[str, str, bool]]:
    pares = []
    bases = list(postos)
    if p["malha"] == "completa":
        todos = [x for b in bases for x in postos[b]]
        pares += [(b, x, False) for b in bases for x in todos]  # toda base atende todo posto
        for n, b in enumerate(bases):
            ps = postos[b]
            pares += [(ps[0], b, False), (ps[1], b, False)]  # volta regular
            pares.append((ps[2], b, n < 2))  # a volta do 3º posto é rara nas duas primeiras
        return pares
    for i, b in enumerate(bases, start=1):
        ps = postos[b]
        pares += [(b, ps[0], False), (ps[0], b, False), (ps[0], ps[1], False)]
        if p["bases"] > 1:
            pares.append((ps[1], ps[2], False))
        if i <= (2 if p["bases"] > 1 else 1):
            pares.append((ps[2], b, True))
    return pares


def gerar(agora: datetime, seed: int, perfil: str = "demo") -> dict:
    p = PERFIS[perfil]
    pontos, trechos = _malha(perfil, seed)
    hoje = hoje_local(agora)
    obs: list[dict] = []
    fut: list[dict] = []
    n_veic = p["veiculos"]
    for off in range(-p["dias"], DIAS_SIMULADOS + 1):
        dia = hoje + timedelta(days=off)
        base_ts = inicio_dia(dia)
        dow = dia.isoweekday()
        rng = random.Random(f"{seed}-{perfil}-{off}")
        rnd, logn = rng.random, rng.lognormvariate
        seq_dia = 0
        for t in trechos:
            for tipo in t["tiposVeiculo"]:
                ft = FATOR_TIPO[tipo]
                for h in range(24):
                    if t["esparso"]:
                        n = 1 if rnd() < P_ESPARSO else 0
                    else:
                        n = peso_hora(h, p["peso_pico"])
                    for _ in range(n):
                        seq_dia += 1
                        tempo = (t["tempoBaseMin"] * fator_hora(h) * fator_dow(dow, h) * ft
                                 * logn(0, SIGMA_RUIDO))
                        if rnd() < P_OUTLIER:
                            tempo *= 2 + rnd()
                        km = t["distanciaBaseKm"] * (1 + (rnd() * 2 - 1) * 0.03)
                        ts = base_ts + timedelta(hours=h, minutes=int(rnd() * 60),
                                                 seconds=int(rnd() * 60))
                        doc = {"origem": t["origem"], "destino": t["destino"],
                               "tipoVeiculo": tipo,
                               "veiculoId": f"VEI-{tipo}-{(seq_dia + off * 7) % n_veic + 1}",
                               "viagemId": f"VIA-{dia:%Y%m%d}-{seq_dia:06d}", "seq": 1,
                               "observadoEm": ts, "distanciaKm": round(km, 2),
                               "tempoMin": round(tempo, 2)}
                        if ts < agora:
                            obs.append(doc)
                        elif ts < agora + timedelta(days=DIAS_SIMULADOS):
                            fut.append(doc)
    return {"pontos": pontos, "trechos": trechos, "observacoes": obs, "futuras": fut}

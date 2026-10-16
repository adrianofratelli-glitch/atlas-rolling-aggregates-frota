"""Gerador sintético determinístico: malha, frota e observações de trechos.

Os perfis são tamanhos de laboratório, não o volume de nenhum cliente. A forma do
tempo de deslocamento segue o que qualquer operador de frota reconhece:

    tempoMin = tempoBaseMin × fatorHora × fatorDow × fatorTipoVeiculo × ruído log-normal

com picos de manhã (7–9h) e tarde (17–19h), madrugada mais rápida, sexta mais lenta,
domingo mais rápido e ~1% de outliers (parada longa) que **não** são filtrados.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from datetime import date, timedelta

from pymongo.database import Database
from pymongo.errors import BulkWriteError

from .janela import inicio_dia

PERFIS = {
    "teste": {"bases": 1, "postos": 10, "veiculos": 8, "dias": 30},
    "small": {"bases": 3, "postos": 40, "veiculos": 60, "dias": 200},
    "escala": {"bases": 6, "postos": 400, "veiculos": 1500, "dias": 200},
}

BASES = [  # (cidade, lon, lat)
    ("Paulínia", -47.15, -22.76), ("Guarulhos", -46.53, -23.45),
    ("Ribeirão Preto", -47.81, -21.18), ("São José dos Campos", -45.89, -23.18),
    ("Sorocaba", -47.46, -23.50), ("Bauru", -49.06, -22.31),
]
TIPOS = [
    {"_id": "TOCO", "descricao": "Toco", "capacidadeM3": 6, "fatorTempo": 1.00},
    {"_id": "TRUCK", "descricao": "Truck", "capacidadeM3": 14, "fatorTempo": 1.05},
    {"_id": "CARRETA", "descricao": "Carreta", "capacidadeM3": 30, "fatorTempo": 1.10},
    {"_id": "BITREM", "descricao": "Bitrem", "capacidadeM3": 45, "fatorTempo": 1.18},
]
MIX_TIPOS = [("TOCO", 0.15), ("TRUCK", 0.30), ("CARRETA", 0.35), ("BITREM", 0.20)]
VIZINHOS = 3          # cada posto atende a rota para os 3 postos mais próximos
SIGMA_RUIDO = 0.12
P_OUTLIER = 0.01
P_ATRASO = 0.05       # 1–72 h depois
P_ATRASO_LONGO = 0.005  # > k dias depois


def fator_hora(h: int) -> float:
    if h < 5:
        return 0.85
    if h < 7:
        return 0.95
    if h < 10:
        return 1.35
    if h < 12:
        return 1.10
    if h < 14:
        return 1.15
    if h < 17:
        return 1.05
    if h < 20:
        return 1.40
    if h < 22:
        return 1.10
    return 0.90


def fator_dow(d: date) -> float:
    # weekday(): 0 = segunda … 6 = domingo
    return {0: 1.05, 4: 1.15, 5: 0.95, 6: 0.85}.get(d.weekday(), 1.0)


def _haversine_km(a, b) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + \
        math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _placa(rng: random.Random) -> str:
    L = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return (f"{rng.choice(L)}{rng.choice(L)}{rng.choice(L)}{rng.randint(0, 9)}"
            f"{rng.choice(L)}{rng.randint(0, 9)}{rng.randint(0, 9)}")


def gerar_malha(perfil: str, seed: int) -> dict:
    p = PERFIS[perfil]
    rng = random.Random(f"{seed}-malha")
    pontos, trechos, veiculos = [], [], []
    bases = []
    for i, (cidade, lon, lat) in enumerate(BASES[:p["bases"]], start=1):
        bid = f"BASE-{i:03d}"
        bases.append((bid, (lon, lat), cidade))
        pontos.append({"_id": bid, "tipo": "base", "nome": f"Base {cidade}", "cidade": cidade,
                       "uf": "SP", "location": {"type": "Point", "coordinates": [lon, lat]}})
    postos_por_base: dict[str, list] = {b[0]: [] for b in bases}
    for j in range(1, p["postos"] + 1):
        bid, (blon, blat), cidade = bases[(j - 1) % len(bases)]
        coord = (round(blon + rng.gauss(0, 0.22), 4), round(blat + rng.gauss(0, 0.18), 4))
        pid = f"POSTO-{j:04d}"
        postos_por_base[bid].append((pid, coord))
        pontos.append({"_id": pid, "tipo": "posto", "nome": f"Posto {j:04d}",
                       "cidade": f"Região {cidade}", "uf": "SP",
                       "location": {"type": "Point", "coordinates": list(coord)}})
    coords = {pt["_id"]: tuple(pt["location"]["coordinates"]) for pt in pontos}

    def trecho(o, d):
        reta = _haversine_km(coords[o], coords[d])
        sinuosidade = random.Random(f"{seed}-{o}-{d}").uniform(1.2, 1.45)
        km = max(round(reta * sinuosidade, 1), 1.5)
        vel = 35 if km < 15 else 55 if km < 60 else 70  # km/h em fluxo livre
        return {"_id": f"{o}|{d}", "origem": o, "destino": d, "distanciaBaseKm": km,
                "tempoBaseMin": round(km / vel * 60, 1)}

    for bid, _, _ in bases:
        postos = postos_por_base[bid]
        for pid, c in postos:
            trechos += [trecho(bid, pid), trecho(pid, bid)]
            perto = sorted((q for q in postos if q[0] != pid),
                           key=lambda q: _haversine_km(c, q[1]))[:VIZINHOS]
            trechos += [trecho(pid, q[0]) for q in perto]
    tipos, pesos = zip(*MIX_TIPOS)
    for v in range(1, p["veiculos"] + 1):
        bid = bases[(v - 1) % len(bases)][0]
        veiculos.append({"_id": f"VEI-{v:04d}", "placa": _placa(rng),
                         "tipoVeiculo": rng.choices(tipos, pesos)[0], "baseId": bid,
                         "ativo": True, "turnoNoturno": rng.random() < 0.2})
    return {"pontos": pontos, "tipos_veiculo": TIPOS, "veiculos": veiculos,
            "trechos": list({t["_id"]: t for t in trechos}.values())}


@dataclass
class Malha:
    veiculos: list[dict]
    trechos: dict[tuple[str, str], dict]
    vizinhos: dict[str, list[str]]
    postos_base: dict[str, list[str]]
    fatores: dict[str, float]

    @classmethod
    def do_banco(cls, db: Database) -> "Malha":
        trechos = {(t["origem"], t["destino"]): t for t in db.trechos.find({}, {"_id": 0})}
        bases = {p["_id"] for p in db.pontos.find({"tipo": "base"}, {"_id": 1})}
        viz: dict[str, list[str]] = {}
        pb: dict[str, list[str]] = {}
        for (o, d) in trechos:
            if o in bases:
                pb.setdefault(o, []).append(d)
            elif d not in bases:
                viz.setdefault(o, []).append(d)
        return cls(veiculos=list(db.veiculos.find({"ativo": True}).sort("_id", 1)),
                   trechos=trechos, vizinhos={k: sorted(v) for k, v in viz.items()},
                   postos_base={k: sorted(v) for k, v in pb.items()},
                   fatores={t["_id"]: t["fatorTempo"] for t in db.tipos_veiculo.find()})


def gerar_dia(malha: Malha, dia: date, seed: int, tz: str, k: int = 3) -> list[dict]:
    """Observações de um dia local. Determinístico por (seed, dia)."""
    rng = random.Random(f"{seed}-{dia.isoformat()}")
    meia_noite = inicio_dia(dia, tz)
    fdow = fator_dow(dia)
    docs, viagem = [], 0
    for v in malha.veiculos:
        postos = malha.postos_base.get(v["baseId"])
        if not postos:
            continue
        ftipo = malha.fatores[v["tipoVeiculo"]]
        n_viagens = 1 if rng.random() < 0.45 else 2
        minuto = (rng.randint(18 * 60, 22 * 60) if v.get("turnoNoturno")
                  else rng.randint(5 * 60, 9 * 60))
        for _ in range(n_viagens):
            if minuto >= 24 * 60 + 6 * 60:  # não começa viagem depois das 06:00 do dia seguinte
                break
            viagem += 1
            vid = f"VIA-{dia:%Y%m%d}-{viagem:05d}"
            atual, rota = rng.choice(postos), []
            rota.append((v["baseId"], atual))
            for _ in range(rng.randint(2, 4) - 1):
                opcoes = [p for p in malha.vizinhos.get(atual, []) if p not in {x for _, x in rota}]
                if not opcoes:
                    break
                prox = rng.choice(opcoes)
                rota.append((atual, prox))
                atual = prox
            rota.append((atual, v["baseId"]))
            for seq, (o, d) in enumerate(rota, start=1):
                t = malha.trechos[(o, d)]
                partida = meia_noite + timedelta(minutes=minuto)
                hora_local = (minuto // 60) % 24
                tempo = (t["tempoBaseMin"] * fator_hora(hora_local) * fdow * ftipo
                         * rng.lognormvariate(0, SIGMA_RUIDO))
                if rng.random() < P_OUTLIER:
                    tempo += rng.uniform(45, 180)  # parada longa: fica na média, de propósito
                km = t["distanciaBaseKm"] * rng.uniform(0.97, 1.03)
                chegada = partida + timedelta(minutes=tempo)
                sorteio = rng.random()
                if sorteio < P_ATRASO_LONGO:
                    ingerido = chegada + timedelta(days=rng.uniform(k + 1, k + 10))
                elif sorteio < P_ATRASO_LONGO + P_ATRASO:
                    ingerido = chegada + timedelta(hours=rng.uniform(1, 72))
                else:
                    ingerido = chegada + timedelta(minutes=rng.uniform(1, 20))
                docs.append({"origem": o, "destino": d, "tipoVeiculo": v["tipoVeiculo"],
                             "veiculoId": v["_id"], "viagemId": vid, "seq": seq,
                             "observadoEm": partida, "ingeridoEm": ingerido,
                             "distanciaKm": round(km, 2), "tempoMin": round(tempo, 2)})
                minuto += int(tempo) + (rng.randint(25, 50) if d != v["baseId"] else 0)
            minuto += rng.randint(30, 90)
    # observações cujo dia local "vazou" para o dia seguinte continuam valendo:
    # a chave é o instante de partida, e o pipeline decide o dia local.
    return docs


def inserir(db: Database, docs: list[dict], relogio=None, lote: int = 10_000) -> float:
    """insert_many(ordered=False) em lotes; devolve docs/s da raw.

    Com `relogio` (instante simulado), só entra na raw o que já foi ingerido até ele;
    o resto espera em `ingestao_pendente` — senão o watermark do job enxergaria
    atrasos que ainda não aconteceram.
    """
    if relogio is not None:
        pend = [d for d in docs if d["ingeridoEm"] > relogio]
        docs = [d for d in docs if d["ingeridoEm"] <= relogio]
        if pend:
            _inserir_ignorando_duplicatas(db.ingestao_pendente, pend)
    t0 = time.perf_counter()
    for i in range(0, len(docs), lote):
        _inserir_ignorando_duplicatas(db.trecho_observacoes, docs[i:i + lote])
    return len(docs) / max(time.perf_counter() - t0, 1e-9)


def _inserir_ignorando_duplicatas(coll, docs: list[dict]) -> int:
    """insert_many(ordered=False) tolerando só E11000 em {viagemId, seq}: reenviar o mesmo
    dia (advance repetido depois de uma falha) não duplica observações."""
    try:
        return len(coll.insert_many(docs, ordered=False).inserted_ids)
    except BulkWriteError as e:
        outros = [w for w in e.details.get("writeErrors", []) if w.get("code") != 11000]
        if outros:
            raise
        return e.details.get("nInserted", 0)


def liberar_pendentes(db: Database, relogio) -> int:
    """Move para a raw o que "chegou" até o relógio simulado."""
    filtro = {"ingeridoEm": {"$lte": relogio}}
    docs = list(db.ingestao_pendente.find(filtro))
    if docs:
        _inserir_ignorando_duplicatas(db.trecho_observacoes, docs)
        db.ingestao_pendente.delete_many({"_id": {"$in": [d["_id"] for d in docs]}})
    return len(docs)

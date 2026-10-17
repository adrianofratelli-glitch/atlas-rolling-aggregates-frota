"""Validators `$jsonSchema` de cada collection.

`validationLevel: strict` + `validationAction: error`: documento fora do contrato não
entra — inclusive data como string, que quebraria todo o cálculo de janela.
"""
from __future__ import annotations

COD = {"bsonType": "string", "minLength": 1}
DATA = {"bsonType": "date"}
# draft 4: exclusiveMinimum é booleano e acompanha minimum (> 0)
NUM_POS = {"bsonType": ["double", "int", "long", "decimal"], "minimum": 0, "exclusiveMinimum": True}
NUM = {"bsonType": ["double", "int", "long", "decimal"]}
INT = {"bsonType": ["int", "long"]}
TIPOS_VEICULO = ["TOCO", "TRUCK", "CARRETA", "BITREM"]


def _obj(required: list[str], props: dict, extra: bool = True) -> dict:
    return {"$jsonSchema": {"bsonType": "object", "required": required,
                            "properties": props, "additionalProperties": extra}}


VALIDATORS: dict[str, dict] = {
    "pontos": _obj(["_id", "tipo", "nome"], {
        "_id": COD, "tipo": {"enum": ["base", "posto"]}, "nome": COD,
        "cidade": {"bsonType": "string"}, "uf": {"bsonType": "string"},
        "location": {"bsonType": "object", "required": ["type", "coordinates"]},
    }),
    "tipos_veiculo": _obj(["_id", "descricao", "fatorTempo"], {
        "_id": {"enum": TIPOS_VEICULO}, "descricao": COD,
        "capacidadeM3": NUM_POS, "fatorTempo": NUM_POS,
    }),
    "veiculos": _obj(["_id", "placa", "tipoVeiculo", "baseId", "ativo"], {
        "_id": COD, "placa": COD, "tipoVeiculo": {"enum": TIPOS_VEICULO},
        "baseId": COD, "ativo": {"bsonType": "bool"},
    }),
    "trechos": _obj(["_id", "origem", "destino", "distanciaBaseKm", "tempoBaseMin"], {
        "_id": COD, "origem": COD, "destino": COD,
        "distanciaBaseKm": NUM_POS, "tempoBaseMin": NUM_POS,
    }),
    "trecho_observacoes": _obj(
        ["origem", "destino", "tipoVeiculo", "veiculoId", "viagemId", "seq",
         "observadoEm", "ingeridoEm", "distanciaKm", "tempoMin"], {
            "origem": COD, "destino": COD, "tipoVeiculo": {"enum": TIPOS_VEICULO},
            "veiculoId": COD, "viagemId": COD, "seq": {**INT, "minimum": 1},
            "observadoEm": DATA, "ingeridoEm": DATA,
            "distanciaKm": NUM_POS, "tempoMin": NUM_POS,
        }),
    "trecho_bucket_diario": _obj(
        ["origem", "destino", "tipoVeiculo", "dataLocal", "hora", "dowCivil",
         "somaMin", "somaKm", "n", "minMin", "maxMin", "atualizadoEm", "runId"], {
            "origem": COD, "destino": COD, "tipoVeiculo": {"enum": TIPOS_VEICULO},
            "dataLocal": DATA, "hora": {**INT, "minimum": 0, "maximum": 23},
            "dowCivil": {**INT, "minimum": 1, "maximum": 7},
            "somaMin": NUM_POS, "somaKm": NUM_POS, "n": {**INT, "minimum": 1},
            "minMin": NUM_POS, "maxMin": NUM_POS, "atualizadoEm": DATA, "runId": COD,
        }),
    "trecho_media_historica": _obj(
        ["origem", "destino", "tipoVeiculo", "dow", "turno", "somaMin", "somaKm", "n",
         "mediaMin", "mediaKm", "janelaInicio", "janelaFim", "asOf", "configVersao",
         "runId", "atualizadoEm"], {
            "origem": COD, "destino": COD, "tipoVeiculo": {"enum": TIPOS_VEICULO},
            # dow 0 = "todos os dias" quando config.incluirDow = false
            "dow": {**INT, "minimum": 0, "maximum": 7}, "turno": COD,
            "somaMin": NUM_POS, "somaKm": NUM_POS, "n": {**INT, "minimum": 1},
            "mediaMin": NUM_POS, "mediaKm": NUM_POS,
            "janelaInicio": DATA, "janelaFim": DATA,
            "asOf": {"bsonType": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
            "configVersao": INT, "runId": COD, "atualizadoEm": DATA,
        }),
    "config": _obj(
        ["_id", "versao", "timezone", "janelaDias", "turnos", "regraNoite",
         "kReprocessamento", "minAmostras", "modoLimpezaCamada2"], {
            "_id": {"enum": ["ativa"]}, "versao": INT, "timezone": COD,
            "janelaDias": {**INT, "minimum": 1}, "turnos": {"bsonType": "array", "minItems": 1},
            "regraNoite": {"enum": ["dia_civil", "dia_operacional"]},
            "kReprocessamento": {**INT, "minimum": 1}, "minAmostras": {**INT, "minimum": 1},
            "modoLimpezaCamada2": {"enum": ["merge_runid", "out"]},
            "modoMaterializacao": {"enum": ["simples", "incremental"]},
            "granularidadeBucket": {"enum": ["turno", "hora"]},
            "incluirDow": {"bsonType": "bool"},
        }),
    "job_runs": _obj(["runId", "asOf", "camada", "status", "iniciadoEm"], {
        "runId": COD, "asOf": COD, "camada": {"enum": ["1", "2", "todas"]},
        "status": {"enum": ["running", "ok", "erro"]},
        "iniciadoEm": DATA, "finalizadoEm": {"bsonType": ["date", "null"]},
        "stats": {"bsonType": "object"}, "erro": {"bsonType": ["string", "null"]},
    }),
    "job_locks": _obj(["_id", "owner", "expiraEm"], {
        "_id": COD, "owner": COD, "expiraEm": DATA,
    }),
}

# Camada 1 com grão de turno: um bucket por dia local civil × turno × dow. O dow entra na
# chave porque, com regraNoite = dia_operacional, o turno N de um dia civil mistura duas
# datas de referência (18–23 h do próprio dia e 0–5 h, que contam no dia anterior).
VALIDATORS["trecho_bucket_turno"] = _obj(
    ["origem", "destino", "tipoVeiculo", "dataLocal", "turno", "dow", "somaMin", "somaKm",
     "n", "minMin", "maxMin", "configVersao", "atualizadoEm", "runId"], {
        "origem": COD, "destino": COD, "tipoVeiculo": {"enum": TIPOS_VEICULO},
        "dataLocal": DATA, "turno": COD, "dow": {**INT, "minimum": 0, "maximum": 7},
        "somaMin": NUM_POS, "somaKm": NUM_POS, "n": {**INT, "minimum": 1},
        "minMin": NUM_POS, "maxMin": NUM_POS, "configVersao": INT,
        "atualizadoEm": DATA, "runId": COD,
    })

# Histórico imutável da config: o fallback deriva dow/turno com a versão que gerou o
# agregado, não com a vigente (podem divergir entre a mudança e o próximo run da camada 2).
VALIDATORS["config_versoes"] = {"$jsonSchema": {
    **VALIDATORS["config"]["$jsonSchema"],
    "properties": {**VALIDATORS["config"]["$jsonSchema"]["properties"], "_id": INT}}}

# Simulação: observações já geradas cujo `ingeridoEm` ainda está no futuro do relógio
# da demo. Mesmo contrato da raw; o `advance` as move para a raw quando "chegam".
VALIDATORS["ingestao_pendente"] = VALIDATORS["trecho_observacoes"]

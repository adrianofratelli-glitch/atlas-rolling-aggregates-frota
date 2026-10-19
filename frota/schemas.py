"""Validators `$jsonSchema` de cada collection (schema v2).

`validationLevel: strict` + `validationAction: error`: documento fora do contrato não
entra — inclusive data como string, que quebraria todo o cálculo de janela.
"""
from __future__ import annotations

COD = {"bsonType": "string", "minLength": 1}
DATA = {"bsonType": "date"}
NUM = {"bsonType": ["double", "int", "long", "decimal"]}
# draft 4: exclusiveMinimum é booleano e acompanha minimum (> 0)
NUM_POS = {**NUM, "minimum": 0, "exclusiveMinimum": True}
NUM_NAO_NEG = {**NUM, "minimum": 0}
INT = {"bsonType": ["int", "long"]}
TIPOS_VEICULO = ["TOCO", "TRUCK", "CARRETA", "BITREM"]


def _obj(required: list[str], props: dict) -> dict:
    return {"$jsonSchema": {"bsonType": "object", "required": required,
                            "properties": props, "additionalProperties": True}}


_OBS_REQ = ["origem", "destino", "tipoVeiculo", "veiculoId", "viagemId", "seq",
            "observadoEm", "distanciaKm", "tempoMin"]
_OBS_PROPS = {
    "origem": COD, "destino": COD, "tipoVeiculo": {"enum": TIPOS_VEICULO},
    "veiculoId": COD, "viagemId": COD, "seq": {**INT, "minimum": 1},
    "observadoEm": DATA, "distanciaKm": NUM_POS, "tempoMin": NUM_POS,
}

VALIDATORS: dict[str, dict] = {
    "pontos": _obj(["_id", "tipo", "nome", "cidade"], {
        "_id": COD, "tipo": {"enum": ["base", "posto"]}, "nome": COD,
        "cidade": {"bsonType": "string"},
    }),
    "trechos": _obj(["_id", "origem", "destino", "distanciaBaseKm", "tempoBaseMin"], {
        "_id": COD, "origem": COD, "destino": COD,
        "distanciaBaseKm": NUM_POS, "tempoBaseMin": NUM_POS,
        "esparso": {"bsonType": "bool"},
        "tiposVeiculo": {"bsonType": "array", "minItems": 1,
                         "items": {"enum": TIPOS_VEICULO}},
    }),
    "trecho_observacoes": _obj(_OBS_REQ, _OBS_PROPS),
    "ingestao_simulada": _obj(_OBS_REQ, _OBS_PROPS),
    "trecho_media_dow_hora": _obj(
        ["origem", "destino", "tipoVeiculo", "dow", "hora", "n", "somaMin", "somaQuadMin",
         "somaKm", "mediaMin", "mediaKm", "janelaInicio", "janelaFim", "dataRef", "runId",
         "atualizadoEm"], {
            "origem": COD, "destino": COD, "tipoVeiculo": {"enum": TIPOS_VEICULO},
            "dow": {**INT, "minimum": 1, "maximum": 7},
            "hora": {**INT, "minimum": 0, "maximum": 23},
            "n": {**INT, "minimum": 1},
            "somaMin": NUM_POS, "somaQuadMin": NUM_POS, "somaKm": NUM_POS,
            "mediaMin": NUM_POS, "mediaKm": NUM_POS,
            "janelaInicio": DATA, "janelaFim": DATA,
            "dataRef": {"bsonType": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
            "runId": COD, "atualizadoEm": DATA,
        }),
    "consultas_salvas": _obj(
        ["_id", "filtro", "n", "somaMin", "somaQuadMin", "somaKm", "periodo", "criadoEm",
         "expiraEm"], {
            "_id": {"bsonType": "string"}, "filtro": {"bsonType": "object"},
            "n": {**INT, "minimum": 0},
            "somaMin": NUM_NAO_NEG, "somaQuadMin": NUM_NAO_NEG, "somaKm": NUM_NAO_NEG,
            "periodo": {"enum": ["absoluto", "relativo"]},
            "criadoEm": DATA, "expiraEm": DATA,
        }),
    "job_runs": _obj(["_id", "origem", "dataRef", "iniciadoEm", "status"], {
        "_id": COD, "origem": {"enum": ["trigger", "botao", "cli", "reset"]},
        "dataRef": {"bsonType": "string"}, "iniciadoEm": DATA, "status": COD,
    }),
}

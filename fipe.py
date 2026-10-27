"""Consulta a tabela FIPE (API publica parallelum) com cache no SQLite."""
import json
import urllib.request
from datetime import datetime, timedelta

from db import conectar

BASE = "https://parallelum.com.br/fipe/api/v1/motos"
VALIDADE = timedelta(days=15)


def _get(path):
    url = BASE + path
    with conectar() as con:
        row = con.execute("SELECT resposta, salvo_em FROM fipe_cache WHERE url=?", (url,)).fetchone()
        if row and datetime.now() - datetime.fromisoformat(row["salvo_em"]) < VALIDADE:
            return json.loads(row["resposta"])
    req = urllib.request.Request(url, headers={"User-Agent": "project-leilao/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        dados = json.loads(r.read().decode("utf-8"))
    with conectar() as con:
        con.execute(
            "INSERT OR REPLACE INTO fipe_cache VALUES (?,?,?)",
            (url, json.dumps(dados), datetime.now().isoformat()),
        )
    return dados


def marcas():
    return _get("/marcas")


def modelos(marca):
    return _get(f"/marcas/{marca}/modelos")["modelos"]


def anos(marca, modelo):
    return _get(f"/marcas/{marca}/modelos/{modelo}/anos")


def valor(marca, modelo, ano):
    return _get(f"/marcas/{marca}/modelos/{modelo}/anos/{ano}")

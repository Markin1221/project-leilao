import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "leilao.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS motos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao TEXT NOT NULL,
    ano TEXT,
    placa TEXT,
    lote TEXT,
    categoria TEXT,
    data_compra TEXT,
    valor_arremate REAL DEFAULT 0,
    fipe REAL DEFAULT 0,
    revenda_alvo REAL DEFAULT 0,
    data_venda TEXT,
    valor_venda REAL,
    obs TEXT
);
CREATE TABLE IF NOT EXISTS gastos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    moto_id INTEGER NOT NULL REFERENCES motos(id) ON DELETE CASCADE,
    data TEXT,
    tipo TEXT,
    descricao TEXT,
    valor REAL NOT NULL
);
-- Etapa 3: resultados do leilao de quinta (Copart Vitoria de Santo Antao)
CREATE TABLE IF NOT EXISTS lotes_leilao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_leilao TEXT,
    patio TEXT,
    lote TEXT,
    descricao TEXT,
    ano TEXT,
    categoria TEXT,
    fipe REAL,
    valor_final REAL,
    vendido INTEGER,
    capturado_em TEXT,
    UNIQUE(data_leilao, lote)
);
CREATE TABLE IF NOT EXISTS fipe_cache (
    url TEXT PRIMARY KEY,
    resposta TEXT,
    salvo_em TEXT
);
"""


def conectar():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def iniciar():
    with conectar() as con:
        con.executescript(SCHEMA)

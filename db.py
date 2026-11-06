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
-- Lotes da Copart (todos os veiculos) (proximos leiloes + resultado)
CREATE TABLE IF NOT EXISTS lotes_leilao (
    ln INTEGER PRIMARY KEY,
    auction_id INTEGER,
    data_leilao TEXT,
    descricao TEXT, marca TEXT, modelo TEXT, versao TEXT,
    ano TEXT, ano_fab TEXT, km REAL,
    categoria TEXT, dano TEXT, condicao TEXT, local_fisico TEXT,
    valor_ref REAL, lance_atual REAL,
    vendedor TEXT, obs TEXT, foto TEXT,
    atualizado_em TEXT,
    valor_final REAL, status_final TEXT, bruto_final TEXT,
    alertado INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS fotos (
    ln INTEGER, seq INTEGER, url_vga TEXT, url_hd TEXT, arquivo TEXT,
    PRIMARY KEY (ln, seq)
);
CREATE TABLE IF NOT EXISTS lances_hist (
    ln INTEGER, ts TEXT, lance REAL
);
CREATE TABLE IF NOT EXISTS precos_mercado (
    chave TEXT PRIMARY KEY, consulta TEXT, mediana REAL, n INTEGER,
    minimo REAL, maximo REAL, atualizado_em TEXT
);
CREATE TABLE IF NOT EXISTS fipe_cache (
    url TEXT PRIMARY KEY,
    resposta TEXT,
    salvo_em TEXT
);
"""


# campos completos do lote (adicionados em bancos antigos automaticamente)
COLUNAS_EXTRAS = [
    ("tipo_veiculo", "TEXT"), ("lote_no_leilao", "INTEGER"), ("chassi", "TEXT"), ("tipo_chassi", "TEXT"),
    ("tipo_documento", "TEXT"), ("blindado", "INTEGER"), ("chave", "TEXT"), ("final_placa", "TEXT"),
    ("combustivel", "TEXT"), ("cor", "TEXT"), ("motor", "TEXT"), ("comitente", "TEXT"), ("patio", "TEXT"),
    ("condicoes_url", "TEXT"), ("vendido", "INTEGER"), ("n_fotos", "INTEGER"),
    ("bruto_lista", "TEXT"), ("bruto_detalhe", "TEXT"),
]


def conectar():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def iniciar():
    with conectar() as con:
        cols = [r[1] for r in con.execute("PRAGMA table_info(lotes_leilao)")]
        if cols and "ln" not in cols:  # tabela antiga (vazia) da primeira versao
            con.execute("DROP TABLE lotes_leilao")
        con.executescript(SCHEMA)
        existentes = {r[1] for r in con.execute("PRAGMA table_info(lotes_leilao)")}
        for col, tipo in COLUNAS_EXTRAS:
            if col not in existentes:
                con.execute(f"ALTER TABLE lotes_leilao ADD COLUMN {col} {tipo}")

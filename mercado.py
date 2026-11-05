"""Preco de mercado: anuncios de motos da OLX em Pernambuco (mesmo modelo e ano)."""
import re
import statistics
import time
from pathlib import Path
import urllib.parse
from datetime import datetime, timedelta

from db import conectar

VALIDADE = timedelta(days=5)

JS_CARDS = """() => [...document.querySelectorAll('section.olx-adcard')].map(c => {
  const a = c.querySelector('a[data-testid="adcard-link"]');
  const km = c.querySelector('[aria-label*="quilômetros"]')?.getAttribute('aria-label') || '';
  const p = c.querySelector('.olx-adcard__price')?.textContent || '';
  return {titulo: a?.title || '', link: a?.href || '', km, preco: p};
})"""


def _num(txt):
    s = re.sub(r"[^\d]", "", txt or "")
    return float(s) if s else None


def chave(marca, modelo, ano):
    return f"{(marca or '').upper()}|{(modelo or '').upper()}|{ano}"


def buscar(page, marca, modelo, ano):
    q = f"{marca} {modelo} {ano}".lower()
    url = "https://www.olx.com.br/autos-e-pecas/motos/estado-pe?q=" + urllib.parse.quote(q)
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    try:  # espera os anuncios aparecerem (a pagina monta por JS)
        page.wait_for_selector("section.olx-adcard", timeout=10000)
    except Exception:
        pass
    cards = page.evaluate(JS_CARDS)
    if not cards:  # guarda a pagina pra descobrir o motivo (bloqueio, layout novo...)
        Path(__file__).with_name("debug_olx.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(Path(__file__).with_name("debug_olx.png")))
        raise RuntimeError(f"pagina sem anuncios (titulo: {page.title()!r}) - salvei debug_olx.html/png")
    tokens = [t for t in re.split(r"\s+", (modelo or "").lower()) if t]
    anuncios = []
    for c in cards:
        t = c["titulo"].lower()
        preco = _num(c["preco"])
        # so o mesmo modelo e ano; descarta preco absurdo (pecas, erro de digitacao)
        if not preco or preco < 2000 or str(ano) not in t or not all(tok in t for tok in tokens):
            continue
        anuncios.append({"titulo": c["titulo"], "preco": preco, "km": _num(c["km"]), "link": c["link"]})
    return url, anuncios


def resumir(anuncios):
    precos = sorted(a["preco"] for a in anuncios)
    if len(precos) >= 4:  # tira os extremos (fora de 1,5x o intervalo interquartil)
        q1, _, q3 = statistics.quantiles(precos, n=4)
        f = 1.5 * (q3 - q1)
        precos = [p for p in precos if q1 - f <= p <= q3 + f]
    if not precos:
        return None
    return {"mediana": statistics.median(precos), "n": len(precos), "minimo": precos[0], "maximo": precos[-1]}


def atualizar_precos(page, motos, log=print):
    """motos: lista de (marca, modelo, ano). Busca so o que estiver vencido."""
    with conectar() as con:
        frescos = {r[0] for r in con.execute("SELECT chave FROM precos_mercado WHERE atualizado_em>=? AND n>0",
                                             ((datetime.now() - VALIDADE).isoformat(),))}
    for marca, modelo, ano in sorted(set(motos)):
        k = chave(marca, modelo, ano)
        if k in frescos:
            continue
        try:
            url, anuncios = buscar(page, marca, modelo, ano)
        except Exception as e:
            log(f"  OLX falhou p/ {k}: {e}")
            continue
        r = resumir(anuncios) or {"mediana": None, "n": 0, "minimo": None, "maximo": None}
        with conectar() as con:
            con.execute("""INSERT OR REPLACE INTO precos_mercado
                           (chave, consulta, mediana, n, minimo, maximo, atualizado_em) VALUES (?,?,?,?,?,?,?)""",
                        (k, url, r["mediana"], r["n"], r["minimo"], r["maximo"],
                         datetime.now().isoformat(timespec="seconds")))
        log(f"  OLX-PE {marca} {modelo} {ano}: {r['n']} anúncios, mediana {r['mediana']}")
        time.sleep(4)


def preco(con, marca, modelo, ano):
    return con.execute("SELECT * FROM precos_mercado WHERE chave=?", (chave(marca, modelo, ano),)).fetchone()

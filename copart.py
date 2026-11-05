"""Robo da Copart.

  python copart.py atualizar        -> puxa as motos dos proximos leiloes do patio e manda alertas
  python copart.py ao-vivo          -> acompanha o leilao de hoje e grava o valor final de cada moto
  python copart.py lote 1157763     -> mostra o detalhe de um lote (aceita o link tambem)
  python copart.py login            -> abre o navegador do robo pra voce logar na Copart

Usa a API publica do proprio site, de dentro de um navegador (Playwright),
devagar e so do seu patio.
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from config import carregar
from db import conectar, iniciar

PERFIL = Path(__file__).parent / "perfil_copart"

# console/log do Windows: nao quebrar com acento ou emoji
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
SITE = "https://www.copart.com.br/"

JS_BUSCA = """async ({aid, pagina}) => {
  const p = new URLSearchParams({'query':'*','filter[MISC]':'auction_id:' + aid,
    'sort':'auction_date_utc asc,brazil_default_sort asc','page':String(pagina),'size':'100',
    'start':String(pagina*100),'defaultSort':'true','showUpComing':'true'});
  const r = await fetch('/public/lots/search', {method:'POST',
    headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:p});
  return await r.json();
}"""


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


@contextmanager
def navegador(visivel=None):
    from playwright.sync_api import sync_playwright
    cfg = carregar()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PERFIL), headless=not (visivel if visivel is not None else cfg["navegador_visivel"]),
            locale="pt-BR", viewport={"width": 1280, "height": 900})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(SITE, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        try:
            yield page
        finally:
            ctx.close()


def get_json(page, url):
    return page.evaluate("async (u) => (await fetch(u)).json()", url)


def leiloes_do_patio(page, patio):
    j = get_json(page, "/public/data/auctionsCalendarList")
    out = []
    for s in j["data"]["saleList"]:
        if s.get("yardNumber") != patio:
            continue
        d = str(s["auctionDate"]["dateAsInt"])
        out.append({"aid": s["auctionNumber"], "data": f"{d[:4]}-{d[4:6]}-{d[6:]}",
                    "inicio": s.get("currentSaleTimeEpoch"),
                    "itens": sum(l.get("itemCount", 0) for l in s.get("laneInfoList") or [])})
    return out


def lotes_do_leilao(page, aid):
    todos, pagina = [], 0
    while True:
        j = page.evaluate(JS_BUSCA, {"aid": aid, "pagina": pagina})
        res = j["data"]["results"]
        todos += res["content"]
        if len(todos) >= res["totalElements"] or not res["content"]:
            return todos
        pagina += 1
        time.sleep(1.5)


def detalhe(page, ln):
    j = get_json(page, f"/public/data/lotdetails/solr/{ln}")
    return (j.get("data") or {}).get("lotDetails") or {}


def num_lote(texto):
    m = re.search(r"(\d{5,})", str(texto))
    return int(m.group(1)) if m else None


def salvar_lote(con, l, data_leilao, aid, det=None):
    det = det or {}
    km = det.get("orr")
    con.execute("""
        INSERT INTO lotes_leilao (ln, auction_id, data_leilao, descricao, marca, modelo, versao, ano, ano_fab, km,
            categoria, dano, condicao, local_fisico, valor_ref, lance_atual, vendedor, obs, foto, atualizado_em)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(ln) DO UPDATE SET auction_id=excluded.auction_id, data_leilao=excluded.data_leilao,
            lance_atual=excluded.lance_atual, condicao=excluded.condicao, dano=excluded.dano,
            local_fisico=excluded.local_fisico, valor_ref=excluded.valor_ref,
            versao=COALESCE(excluded.versao, versao), km=COALESCE(excluded.km, km),
            obs=COALESCE(excluded.obs, obs), atualizado_em=excluded.atualizado_em
    """, (l["ln"], aid, data_leilao, l.get("ld"), l.get("mkn"), l.get("lm"), det.get("version"),
          l.get("lcy"), l.get("manufactureYear"), km if km else None, l.get("lossType"),
          l.get("damageClassification"), l.get("drivabilityRating"), l.get("yn"),
          float(l.get("la") or 0), float(l.get("hb") or 0), l.get("sellerName"), det.get("cmmnts"),
          l.get("tims"), datetime.now().isoformat(timespec="seconds")))


# ---------------- alertas ----------------
def telegram(cfg, texto):
    if not (cfg["telegram_token"] and cfg["telegram_chat_id"]):
        log("[alerta sem Telegram configurado]", texto.replace("\n", " | "))
        return
    dados = urllib.parse.urlencode({"chat_id": cfg["telegram_chat_id"], "text": texto,
                                    "disable_web_page_preview": "true"}).encode()
    url = f"https://api.telegram.org/bot{cfg['telegram_token']}/sendMessage"
    try:
        urllib.request.urlopen(url, dados, timeout=15).read()
    except Exception as e:
        log("Falha ao mandar Telegram:", e)


def bate_interesse(lote, it):
    if it.get("modelo") and it["modelo"].lower() not in (lote["descricao"] or "").lower():
        return False
    if it.get("ano_min") and int(lote["ano"] or 0) < int(it["ano_min"]):
        return False
    if it.get("lance_ate") and (lote["lance_atual"] or 0) > float(it["lance_ate"]):
        return False
    return True


def alertar(cfg):
    with conectar() as con:
        novos = con.execute("SELECT * FROM lotes_leilao WHERE alertado=0 AND data_leilao>=?",
                            (date.today().isoformat(),)).fetchall()
        for l in novos:
            if any(bate_interesse(l, it) for it in cfg["interesses"]):
                fora = "" if "VIT" in (l["local_fisico"] or "").upper() else f"\n⚠️ Fica em {l['local_fisico']} (frete)"
                telegram(cfg, f"🏍️ {l['descricao']} — lote {l['ln']}\nLeilão {l['data_leilao']}\n"
                              f"Ref.: R$ {l['valor_ref']:,.0f} · Lance atual: R$ {l['lance_atual']:,.0f}\n"
                              f"{l['categoria']} · {l['condicao']}{fora}\n{SITE}lot/{l['ln']}")
                con.execute("UPDATE lotes_leilao SET alertado=1 WHERE ln=?", (l["ln"],))


# ---------------- comandos ----------------
def atualizar():
    cfg = carregar()
    iniciar()
    with navegador() as page:
        leiloes = [x for x in leiloes_do_patio(page, cfg["patio"]) if x["data"] >= date.today().isoformat()]
        log(f"{len(leiloes)} leilão(ões) do pátio {cfg['patio']}")
        for lei in leiloes:
            lotes = [l for l in lotes_do_leilao(page, lei["aid"]) if l.get("vehicleType") == "Motos"]
            log(f"  {lei['data']} (leilão {lei['aid']}): {len(lotes)} motos")
            with conectar() as con:
                conhecidos = {r[0] for r in con.execute("SELECT ln FROM lotes_leilao WHERE versao IS NOT NULL")}
            for l in lotes:
                det = None
                if l["ln"] not in conhecidos:  # detalhe so na primeira vez
                    time.sleep(1.5)
                    det = detalhe(page, l["ln"])
                with conectar() as con:
                    salvar_lote(con, l, lei["data"], lei["aid"], det)
        # preco de mercado (OLX-PE) das motos que vao a leilao
        with conectar() as con:
            motos = con.execute("SELECT DISTINCT marca, modelo, ano FROM lotes_leilao WHERE data_leilao>=?",
                                (date.today().isoformat(),)).fetchall()
        if cfg.get("pesquisar_olx"):
            log(f"Pesquisando preço de mercado de {len(motos)} modelo(s)…")
            import mercado
            mercado.atualizar_precos(page, [tuple(m) for m in motos], log=log)
    alertar(cfg)
    log("Pronto.")


def finalizar(con, page, ln, motivo):
    det = detalhe(page, ln)
    valor = det.get("awardedHighBid") or det.get("currBid") or det.get("hb") or None
    if not valor:
        row = con.execute("SELECT lance_atual FROM lotes_leilao WHERE ln=?", (ln,)).fetchone()
        valor = row[0] if row else None
    con.execute("UPDATE lotes_leilao SET valor_final=?, status_final=?, bruto_final=? WHERE ln=?",
                (valor, f"{det.get('saleStatus') or ''} {det.get('bidStatus') or ''} ({motivo})".strip(),
                 json.dumps(det, ensure_ascii=False), ln))
    log(f"  lote {ln}: final R$ {valor} [{det.get('saleStatus')}/{det.get('bidStatus')}] ({motivo})")


def ao_vivo(data_alvo=None):
    cfg = carregar()
    iniciar()
    data_alvo = data_alvo or date.today().isoformat()
    with navegador() as page:
        lei = next((x for x in leiloes_do_patio(page, cfg["patio"]) if x["data"] == data_alvo), None)
        if not lei:
            log("Nenhum leilão do pátio hoje.")
            return
        if lei["inicio"]:
            espera = lei["inicio"] / 1000 - time.time() - 300
            if espera > 0:
                log(f"Leilão às {datetime.fromtimestamp(lei['inicio']/1000):%H:%M}. Esperando {espera/60:.0f} min…")
                time.sleep(espera)
        log(f"Acompanhando leilão {lei['aid']}")
        pendentes, fim = {}, time.time() + 5 * 3600
        while time.time() < fim:
            try:
                lotes = lotes_do_leilao(page, lei["aid"])
            except Exception as e:
                log("Erro ao buscar lotes:", e)
                page.reload()
                time.sleep(30)
                continue
            agora = {l["ln"]: l for l in lotes if l.get("vehicleType") == "Motos"}
            with conectar() as con:
                for ln, l in agora.items():
                    salvar_lote(con, l, lei["data"], lei["aid"])
                    con.execute("INSERT INTO lances_hist (ln, ts, lance) VALUES (?,?,?)",
                                (ln, datetime.now().isoformat(timespec="seconds"), float(l.get("hb") or 0)))
                    pendentes[ln] = True
                # moto que sumiu da lista = ja foi leiloada
                for ln in [x for x in pendentes if x not in agora]:
                    finalizar(con, page, ln, "saiu da lista")
                    del pendentes[ln]
                    time.sleep(1)
            if not agora:
                log("Nenhuma moto restante na lista.")
                break
            time.sleep(60)
        with conectar() as con:
            for ln in pendentes:
                finalizar(con, page, ln, "fim do acompanhamento")
    log("Leilão encerrado.")


def mostrar_lote(texto):
    ln = num_lote(texto)
    with navegador() as page:
        print(json.dumps(detalhe(page, ln), indent=2, ensure_ascii=False))


def login():
    with navegador(visivel=True) as page:
        page.goto(SITE + "login", wait_until="domcontentloaded")
        input("Faça login na janela que abriu e depois aperte ENTER aqui…")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "atualizar"
    if cmd == "atualizar":
        atualizar()
    elif cmd == "ao-vivo":
        ao_vivo(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "lote":
        mostrar_lote(sys.argv[2])
    elif cmd == "login":
        login()
    else:
        print(__doc__)

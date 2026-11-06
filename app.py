from datetime import date
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for

import fipe
import mercado
from config import carregar
from calc import CATEGORIAS, analisar, brl, padroes, parse_br
from db import conectar, iniciar

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.jinja_env.filters["brl"] = brl
def nome_bonito(t):
    """'2017 HONDA XRE 300' -> '2017 Honda XRE 300'; siglas e codigos ficam em maiusculas."""
    def w(x):
        if any(c.isdigit() for c in x) or len(x) <= 3 or "-" in x:
            return x.upper() if len(x) <= 3 else x
        return x.capitalize()
    return " ".join(w(x) for x in str(t or "").split())


app.jinja_env.filters["nome"] = nome_bonito
app.jinja_env.filters["brl100"] = lambda v: brl(round(v / 100) * 100) if v else brl(v)

CAMPOS_CALC = ["fipe", "revenda", "fator", "lance", "comissao_pct", "taxas", "debitos", "manutencao",
               "reserva_pct", "documentacao", "frete", "outros", "margem_alvo"]


def hoje():
    return date.today().isoformat()


def resumo_moto(con, m):
    gastos = con.execute("SELECT COALESCE(SUM(valor),0) FROM gastos WHERE moto_id=?", (m["id"],)).fetchone()[0]
    custo = (m["valor_arremate"] or 0) + gastos
    fim = m["data_venda"] or hoje()
    dias = (date.fromisoformat(fim) - date.fromisoformat(m["data_compra"])).days if m["data_compra"] else 0
    lucro = (m["valor_venda"] - custo) if m["valor_venda"] is not None else None
    return {**dict(m), "custo": custo, "gastos": gastos, "dias": dias, "lucro": lucro,
            "categoria_nome": CATEGORIAS.get(m["categoria"], m["categoria"] or "-")}


@app.route("/")
def painel():
    with conectar() as con:
        motos = [resumo_moto(con, m) for m in con.execute("SELECT * FROM motos ORDER BY data_compra DESC, id DESC")]
    estoque = [m for m in motos if m["valor_venda"] is None]
    vendidas = [m for m in motos if m["valor_venda"] is not None]
    totais = {
        "parado": sum(m["custo"] for m in estoque),
        "lucro": sum(m["lucro"] for m in vendidas),
        "vendidas": len(vendidas),
        "margem": (sum(m["lucro"] for m in vendidas) / (sum(m["custo"] for m in vendidas) or 1)) if vendidas else 0,
    }
    return render_template("painel.html", estoque=estoque, vendidas=vendidas, t=totais)


@app.route("/calculadora", methods=["GET", "POST"])
def calculadora():
    form = request.form if request.method == "POST" else request.args
    dados = {"categoria": form.get("categoria", "financiamento"), "descricao": form.get("descricao", ""),
             "ano": form.get("ano", ""), "lote": form.get("lote", "")}
    cfg = carregar()
    defaults = {"comissao_pct": cfg["comissao_pct"], "margem_alvo": cfg["margem_alvo"],
                "reserva_pct": cfg["reserva_pct"], "taxas": cfg["taxas_padrao"],
                "documentacao": cfg["documentacao_padrao"]}
    for c in CAMPOS_CALC:
        dados[c] = parse_br(form.get(c), defaults.get(c, 0))
    res = analisar(dados, cfg) if dados["fipe"] or dados["revenda"] else None
    return render_template("calculadora.html", d=dados, r=res, categorias=CATEGORIAS, raw=form,
                           defaults=defaults, pad=padroes(dados["categoria"], cfg),
                           cfg_p={"venda": cfg["pessimista_venda_pct"], "manut": cfg["pessimista_manutencao_x"]})


@app.route("/motos/nova", methods=["POST"])
def moto_nova():
    f = request.form
    lance = parse_br(f.get("lance"))
    with conectar() as con:
        cur = con.execute(
            """INSERT INTO motos (descricao, ano, placa, lote, categoria, data_compra, valor_arremate, fipe, revenda_alvo, obs)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (f.get("descricao") or "Moto sem nome", f.get("ano"), f.get("placa"), f.get("lote"),
             f.get("categoria"), f.get("data_compra") or hoje(), lance, parse_br(f.get("fipe")),
             parse_br(f.get("revenda")), f.get("obs")),
        )
        mid = cur.lastrowid
        # custos que ja sao conhecidos na hora da compra
        iniciais = [("Leilao", "Comissao do leiloeiro", lance * parse_br(f.get("comissao_pct"), 5) / 100),
                    ("Leilao", "Taxas do leilao (adm/patio)", parse_br(f.get("taxas"))),
                    ("Debitos", "Debitos do veiculo", parse_br(f.get("debitos")))]
        for tipo, desc, v in iniciais:
            if v:
                con.execute("INSERT INTO gastos (moto_id, data, tipo, descricao, valor) VALUES (?,?,?,?,?)",
                            (mid, f.get("data_compra") or hoje(), tipo, desc, round(v, 2)))
    return redirect(url_for("moto", mid=mid))


@app.route("/motos/<int:mid>")
def moto(mid):
    with conectar() as con:
        m = con.execute("SELECT * FROM motos WHERE id=?", (mid,)).fetchone()
        if not m:
            return redirect(url_for("painel"))
        gastos = con.execute("SELECT * FROM gastos WHERE moto_id=? ORDER BY data, id", (mid,)).fetchall()
        r = resumo_moto(con, m)
    return render_template("moto.html", m=r, gastos=gastos, hoje=hoje())


@app.route("/motos/<int:mid>/gasto", methods=["POST"])
def gasto_novo(mid):
    f = request.form
    with conectar() as con:
        con.execute("INSERT INTO gastos (moto_id, data, tipo, descricao, valor) VALUES (?,?,?,?,?)",
                    (mid, f.get("data") or hoje(), f.get("tipo"), f.get("descricao"), parse_br(f.get("valor"))))
    return redirect(url_for("moto", mid=mid))


@app.route("/gastos/<int:gid>/remover", methods=["POST"])
def gasto_remover(gid):
    with conectar() as con:
        row = con.execute("SELECT moto_id FROM gastos WHERE id=?", (gid,)).fetchone()
        con.execute("DELETE FROM gastos WHERE id=?", (gid,))
    return redirect(url_for("moto", mid=row["moto_id"]) if row else url_for("painel"))


@app.route("/motos/<int:mid>/venda", methods=["POST"])
def moto_venda(mid):
    f = request.form
    valor = f.get("valor_venda", "").strip()
    with conectar() as con:
        if valor:
            con.execute("UPDATE motos SET valor_venda=?, data_venda=? WHERE id=?",
                        (parse_br(valor), f.get("data_venda") or hoje(), mid))
        else:  # desfazer venda
            con.execute("UPDATE motos SET valor_venda=NULL, data_venda=NULL WHERE id=?", (mid,))
    return redirect(url_for("moto", mid=mid))


@app.route("/motos/<int:mid>/remover", methods=["POST"])
def moto_remover(mid):
    with conectar() as con:
        con.execute("DELETE FROM motos WHERE id=?", (mid,))
    return redirect(url_for("painel"))


# ---------------- Copart ----------------
def categoria_lote(l):
    cat, dano = (l["categoria"] or "").upper(), (l["dano"] or "").upper()
    doc = (l.get("tipo_documento") if isinstance(l, dict) else (l["tipo_documento"] if "tipo_documento" in l.keys() else "")) or ""
    if "GRANDE" in dano or "IRRECUP" in dano or "IRRECUP" in doc.upper() or "SUCATA" in doc.upper():
        return "sucata"
    if "MÉDIA" in dano or "MEDIA" in dano:
        return "media"
    if "PEQUENA" in dano:
        return "pequena"
    if "ROUBO" in cat or "FURTO" in cat:
        return "roubo"
    if "FINANC" in cat:
        return "financiamento"
    return "pequena"  # colisao sem classificacao: conservador


def pct_tipico(con, l):
    """Quanto (% da referencia) essa moto costuma sair no leilao, pelo historico."""
    q = """SELECT AVG(valor_final / valor_ref), COUNT(*) FROM lotes_leilao
           WHERE valor_final > 0 AND valor_ref > 0 AND {}"""
    for filtro, args, nome in (("marca=? AND modelo=?", (l["marca"], l["modelo"]), "mesmo modelo"),
                               ("categoria=?", (l["categoria"],), "mesma categoria")):
        pct, n = con.execute(q.format(filtro), args).fetchone()
        if n:
            return pct, n, nome
    return None, 0, None


def analisar_lote(con, l, cfg):
    fora = "VIT" not in (l["local_fisico"] or "").upper()
    pct, n, base = pct_tipico(con, l)
    previsto = max((l["valor_ref"] or 0) * pct, l["lance_atual"] or 0) if pct else None
    cat = categoria_lote(l)
    mkt = mercado.preco(con, l["marca"], l["modelo"], l["ano"])
    revenda = mkt["mediana"] * cfg["fator_sobre_anuncio"].get(cat, 0.8) if mkt and mkt["mediana"] else 0
    d = {"fipe": l["valor_ref"] or 0, "categoria": cat, "revenda": revenda,
         "carro": (l["tipo_veiculo"] or "Motos") != "Motos",
         "lance": previsto or l["lance_atual"] or 0,
         "taxas": cfg["taxas_padrao"], "documentacao": cfg["documentacao_padrao"],
         "frete": cfg["frete_outro_patio"] if fora else cfg["frete_local"]}
    return d, analisar(d, cfg), fora, {"previsto": previsto, "n": n, "base": base, "mkt": mkt}


@app.route("/sugestoes")
def sugestoes():
    cfg = carregar()
    tipo = request.args.get("tipo", "Motos")
    with conectar() as con:
        tipos = [r[0] for r in con.execute("""SELECT tipo_veiculo, COUNT(*) FROM lotes_leilao WHERE data_leilao>=?
                    AND tipo_veiculo IS NOT NULL GROUP BY tipo_veiculo
                    ORDER BY tipo_veiculo<>'Motos', COUNT(*) DESC""", (hoje(),))]
        filtro, args = ("", (hoje(),)) if tipo == "todos" else (" AND tipo_veiculo=?", (hoje(), tipo))
        lotes = con.execute("SELECT * FROM lotes_leilao WHERE data_leilao>=?" + filtro + " ORDER BY data_leilao, ln",
                            args).fetchall()
        ult = con.execute("SELECT MAX(atualizado_em) FROM lotes_leilao").fetchone()[0]
        itens = []
        for l in lotes:
            d, r, fora, tip = analisar_lote(con, l, cfg)
            itens.append({"l": l, "d": d, "r": r, "fora": fora, "tip": tip,
                          "folga": r["lance_max"] - (tip["previsto"] or l["lance_atual"] or 0)})
    itens.sort(key=lambda x: (x["l"]["data_leilao"], -x["folga"]))
    return render_template("sugestoes.html", itens=itens, ult=ult, cfg=cfg, categorias=CATEGORIAS,
                           tipos=tipos, tipo=tipo)


CAMPOS_FICHA = [("lote_no_leilao", "Lote no leilão"), ("ln", "Código"), ("descricao", "Descrição"),
                ("versao", "Versão"), ("ano_fab", "Fabricação"), ("ano", "Modelo"), ("marca", "Marca"),
                ("modelo", "Modelo (nome)"), ("tipo_veiculo", "Categoria"), ("valor_ref", "FIPE / ref."),
                ("tipo_documento", "Tipo de documento"), ("dano", "Tipo de monta"), ("tipo_chassi", "Tipo de chassi"),
                ("blindado", "Blindado"), ("categoria", "Condição"), ("condicao", "Condição func."),
                ("chassi", "Chassi"), ("chave", "Chave"), ("final_placa", "Final da placa"), ("km", "Km"),
                ("combustivel", "Combustível"), ("motor", "Motor"), ("cor", "Cor"), ("patio", "Pátio"),
                ("local_fisico", "Local físico"), ("comitente", "Comitente"), ("vendedor", "Vendedor"),
                ("obs", "Complemento"), ("data_leilao", "Data do leilão"), ("lance_atual", "Lance atual"),
                ("valor_final", "Valor final"), ("status_final", "Resultado")]


@app.route("/veiculos")
def veiculos():
    a = request.args
    where, args = ["1=1"], []
    if a.get("q"):
        where.append("(descricao LIKE ? OR versao LIKE ? OR chassi LIKE ? OR CAST(ln AS TEXT)=?)")
        args += [f"%{a['q']}%"] * 3 + [a["q"]]
    for campo, col in (("tipo", "tipo_veiculo"), ("data", "data_leilao"), ("cat", "categoria")):
        if a.get(campo):
            where.append(f"{col}=?")
            args.append(a[campo])
    situacao = a.get("sit", "")
    if situacao == "vendido":
        where.append("vendido=1")
    elif situacao == "nao":
        where.append("vendido=0")
    elif situacao == "aberto":
        where.append("valor_final IS NULL")
    ordens = {"data": "data_leilao DESC, lote_no_leilao, ln", "final": "valor_final DESC",
              "ref": "valor_ref DESC", "pct": "valor_final / NULLIF(valor_ref,0) DESC", "nome": "descricao"}
    ordem = ordens.get(a.get("ord"), ordens["data"])
    pagina = max(int(a.get("p", 1) or 1), 1)
    with conectar() as con:
        filtro = " AND ".join(where)
        total, soma_final, n_final = con.execute(
            f"SELECT COUNT(*), SUM(valor_final), COUNT(valor_final) FROM lotes_leilao WHERE {filtro}", args).fetchone()
        lotes = con.execute(f"SELECT * FROM lotes_leilao WHERE {filtro} ORDER BY {ordem} LIMIT 50 OFFSET ?",
                            args + [(pagina - 1) * 50]).fetchall()
        opcoes = {
            "tipo": [r[0] for r in con.execute("SELECT DISTINCT tipo_veiculo FROM lotes_leilao WHERE tipo_veiculo IS NOT NULL ORDER BY 1")],
            "data": [r[0] for r in con.execute("SELECT DISTINCT data_leilao FROM lotes_leilao ORDER BY 1 DESC")],
            "cat": [r[0] for r in con.execute("SELECT DISTINCT categoria FROM lotes_leilao WHERE categoria IS NOT NULL ORDER BY 1")],
        }
        miniaturas = {r[0]: r[1] for r in con.execute(
            "SELECT ln, arquivo FROM fotos WHERE seq=1 AND arquivo IS NOT NULL AND ln IN (%s)"
            % ",".join(str(l["ln"]) for l in lotes) if lotes else "SELECT 1, 1 WHERE 0")}
    return render_template("veiculos.html", lotes=lotes, total=total, pagina=pagina, a=a, opcoes=opcoes,
                           paginas=(total + 49) // 50, miniaturas=miniaturas,
                           media_final=(soma_final / n_final) if n_final else None, n_final=n_final)


@app.route("/lotes/<int:ln>")
def ficha_lote(ln):
    import json as _json
    with conectar() as con:
        l = con.execute("SELECT * FROM lotes_leilao WHERE ln=?", (ln,)).fetchone()
        if not l:
            return redirect(url_for("sugestoes"))
        fotos = con.execute("SELECT * FROM fotos WHERE ln=? ORDER BY seq", (ln,)).fetchall()
        lances = con.execute("SELECT ts, lance FROM lances_hist WHERE ln=? ORDER BY ts", (ln,)).fetchall()
        d, r, fora, tip = analisar_lote(con, l, carregar())
    campos = []
    for k, nome in CAMPOS_FICHA:
        v = l[k]
        if v in (None, ""):
            continue
        if k == "blindado":
            v = "Sim" if v else "Não"
        elif k in ("valor_ref", "lance_atual", "valor_final"):
            v = brl(v)
        elif k == "km":
            v = f"{v:,.0f}".replace(",", ".")
        campos.append((nome, v))
    extras = {}
    for col in ("bruto_detalhe", "bruto_lista"):
        try:
            extras.update({k: v for k, v in _json.loads(l[col] or "{}").items() if v not in (None, "", 0, [])})
        except ValueError:
            pass
    return render_template("lote.html", l=l, campos=campos, fotos=fotos, lances=lances,
                           extras=sorted(extras.items()), an={"d": d, "r": r, "fora": fora, "tip": tip},
                           categorias=CATEGORIAS)


@app.route("/fotos/<path:arq>")
def foto(arq):
    from flask import send_from_directory
    return send_from_directory(Path(__file__).parent / "fotos", arq)


@app.route("/historico")
def historico():
    with conectar() as con:
        lotes = con.execute("""SELECT * FROM lotes_leilao WHERE valor_final IS NOT NULL
                               ORDER BY data_leilao DESC, ln""").fetchall()
        resumo = con.execute("""SELECT marca || ' ' || modelo AS moto, COUNT(*) n,
                                  AVG(valor_final) media, AVG(valor_final / NULLIF(valor_ref,0)) pct
                                FROM lotes_leilao WHERE valor_final > 0
                                GROUP BY moto ORDER BY n DESC""").fetchall()
    return render_template("historico.html", lotes=lotes, resumo=resumo)


@app.route("/lote")
def lote_link():
    """Analisa um lote colando o link ou o numero."""
    import copart
    ln = copart.num_lote(request.args.get("l", ""))
    if not ln:
        return redirect(url_for("sugestoes"))
    with copart.navegador() as page:
        det = copart.detalhe(page, ln)
    if not det.get("ln"):
        return render_template("sugestoes.html", itens=[], ult=None, cfg=carregar(), categorias=CATEGORIAS,
                               erro=f"Lote {ln} não encontrado na Copart.")
    l = {"categoria": det.get("lt"), "dano": det.get("dtd"), "local_fisico": det.get("yn"),
         "tipo_documento": det.get("stt")}
    q = {"fipe": f"{det.get('la') or 0:.2f}".replace(".", ","), "lance": f"{det.get('currBid') or 0:.2f}".replace(".", ","),
         "descricao": f"{det.get('mkn','')} {det.get('version') or det.get('lm','')}".strip(),
         "ano": det.get("lcy", ""), "lote": ln, "categoria": categoria_lote(l)}
    return redirect(url_for("calculadora", **q))


# ---- FIPE (o navegador pede, o servidor busca e guarda em cache) ----
def _fipe(fn, *a):
    try:
        return jsonify(fn(*a))
    except Exception as e:  # sem internet, limite da API etc.
        return jsonify({"erro": str(e)}), 502


@app.route("/api/fipe/marcas")
def api_marcas():
    return _fipe(fipe.marcas)


@app.route("/api/fipe/<marca>/modelos")
def api_modelos(marca):
    return _fipe(fipe.modelos, marca)


@app.route("/api/fipe/<marca>/<modelo>/anos")
def api_anos(marca, modelo):
    return _fipe(fipe.anos, marca, modelo)


@app.route("/api/fipe/<marca>/<modelo>/<ano>")
def api_valor(marca, modelo, ano):
    return _fipe(fipe.valor, marca, modelo, ano)


if __name__ == "__main__":
    iniciar()
    # host 0.0.0.0 = acessivel pelo celular na mesma Wi-Fi
    app.run(host="0.0.0.0", port=5000, debug=False)

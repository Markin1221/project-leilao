from datetime import date

from flask import Flask, jsonify, redirect, render_template, request, url_for

import fipe
from calc import CATEGORIAS, analisar, brl, parse_br
from db import conectar, iniciar

app = Flask(__name__)
app.jinja_env.filters["brl"] = brl

CAMPOS_CALC = ["fipe", "revenda", "fator", "lance", "comissao_pct", "taxas", "debitos",
               "reparo", "documentacao", "frete", "margem_alvo"]


def hoje():
    return date.today().isoformat()


def resumo_moto(con, m):
    gastos = con.execute("SELECT COALESCE(SUM(valor),0) FROM gastos WHERE moto_id=?", (m["id"],)).fetchone()[0]
    custo = (m["valor_arremate"] or 0) + gastos
    fim = m["data_venda"] or hoje()
    dias = (date.fromisoformat(fim) - date.fromisoformat(m["data_compra"])).days if m["data_compra"] else 0
    lucro = (m["valor_venda"] - custo) if m["valor_venda"] is not None else None
    return {**dict(m), "custo": custo, "gastos": gastos, "dias": dias, "lucro": lucro,
            "categoria_nome": CATEGORIAS.get(m["categoria"], (m["categoria"] or "-",))[0]}


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
    defaults = {"comissao_pct": 5, "margem_alvo": 20}
    for c in CAMPOS_CALC:
        dados[c] = parse_br(form.get(c), defaults.get(c, 0))
    res = analisar(dados) if dados["fipe"] or dados["revenda"] else None
    return render_template("calculadora.html", d=dados, r=res, categorias=CATEGORIAS, raw=form)


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

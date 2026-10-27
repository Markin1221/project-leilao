"""Calculo de viabilidade de um lote de leilao."""

# Fator inicial de revenda sobre a FIPE por categoria do lote.
# Sao chutes iniciais: ajuste com o que voce ve nos anuncios e,
# depois, com o historico dos leiloes de quinta.
CATEGORIAS = {
    "financiamento": ("Recuperada de financiamento", 0.95),
    "roubo": ("Recuperada de roubo/furto", 0.90),
    "pequena": ("Sinistro pequena monta", 0.85),
    "media": ("Sinistro media monta", 0.70),
    "sucata": ("Sucata / baixa (nao volta a rodar)", 0.0),
}


def parse_br(valor, padrao=0.0):
    """Aceita '8.500,00', '8500', 'R$ 8.500,50', '5%'."""
    if valor is None:
        return padrao
    s = str(valor).replace("R$", "").replace("%", "").strip()
    if not s:
        return padrao
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return padrao


def brl(v):
    if v is None:
        return "-"
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-R$ " if v < 0 else "R$ ") + s


def analisar(d):
    """d: dict com numeros ja convertidos. Retorna dict de resultado."""
    fipe = d.get("fipe", 0)
    cat = d.get("categoria", "financiamento")
    fator = d.get("fator") or CATEGORIAS.get(cat, ("", 0.9))[1]
    revenda = d.get("revenda") or fipe * fator
    lance = d.get("lance", 0)
    com = d.get("comissao_pct", 5) / 100
    fixos = sum(d.get(k, 0) for k in ("taxas", "debitos", "reparo", "documentacao", "frete"))
    margem_alvo = d.get("margem_alvo", 20) / 100

    comissao = lance * com
    custo = lance + comissao + fixos
    lucro = revenda - custo
    margem = lucro / custo if custo else 0
    # custo maximo para ter a margem alvo: revenda / (1 + m)
    lance_max = (revenda / (1 + margem_alvo) - fixos) / (1 + com) if revenda else 0

    if cat == "sucata":
        veredito = ("ruim", "Sucata nao pode voltar a circular. So vale para pecas.")
    elif not lance:
        veredito = ("info", f"Lance maximo para {d.get('margem_alvo', 20):.0f}% de margem: {brl(max(lance_max, 0))}")
    elif margem >= margem_alvo:
        veredito = ("bom", "Vale a pena nesse lance.")
    elif margem > 0:
        veredito = ("medio", "Da lucro, mas abaixo da margem que voce quer.")
    else:
        veredito = ("ruim", "Prejuizo nesse lance.")

    return {
        "revenda": revenda,
        "fator": fator,
        "comissao": comissao,
        "fixos": fixos,
        "custo": custo,
        "lucro": lucro,
        "margem": margem,
        "lance_max": max(lance_max, 0),
        "veredito": veredito,
    }

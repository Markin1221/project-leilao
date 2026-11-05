"""Calculo de viabilidade de um lote de leilao."""
from config import carregar

CATEGORIAS = {
    "financiamento": "Recuperada de financiamento",
    "roubo": "Recuperada de roubo/furto",
    "pequena": "Sinistro pequena monta",
    "media": "Sinistro media monta",
    "sucata": "Sucata / baixa (nao volta a rodar)",
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


def padroes(categoria, cfg=None):
    cfg = cfg or carregar()
    return {"fator": cfg["fator_revenda"].get(categoria, 0.8),
            "manutencao": cfg["manutencao_padrao"].get(categoria, 1500)}


def _cenario(lance, revenda, manutencao, fixos, com, reserva):
    comissao = lance * com
    base = lance + comissao + fixos + manutencao
    reserva_v = base * reserva
    custo = base + reserva_v
    lucro = revenda - custo
    return {"revenda": revenda, "comissao": comissao, "manutencao": manutencao, "reserva": reserva_v,
            "custo": custo, "lucro": lucro, "margem": lucro / custo if custo else 0}


def analisar(d, cfg=None):
    """d: dict com numeros. Campos vazios (0) usam os padroes do config.json."""
    cfg = cfg or carregar()
    cat = d.get("categoria", "financiamento")
    pad = padroes(cat, cfg)
    fipe = d.get("fipe", 0)
    fator = d.get("fator") or pad["fator"]
    revenda = d.get("revenda") or fipe * fator
    manut = d.get("manutencao") or pad["manutencao"]
    lance = d.get("lance", 0)
    com = d.get("comissao_pct", cfg["comissao_pct"]) / 100
    reserva = d.get("reserva_pct", cfg["reserva_pct"]) / 100
    fixos = sum(d.get(k, 0) for k in ("taxas", "debitos", "documentacao", "frete", "outros"))
    m_alvo = d.get("margem_alvo", cfg["margem_alvo"]) / 100

    esperado = _cenario(lance, revenda, manut, fixos, com, reserva)
    # pessimista: vende 10% abaixo e a manutencao sai o dobro
    pess = _cenario(lance, revenda * (1 - cfg["pessimista_venda_pct"] / 100),
                    manut * cfg["pessimista_manutencao_x"], fixos, com, reserva)

    # maior lance que ainda da a margem alvo no cenario esperado:
    # revenda = (L(1+com) + fixos + manut)(1+reserva)(1+m)
    lance_max = (revenda / ((1 + reserva) * (1 + m_alvo)) - fixos - manut) / (1 + com) if revenda else 0
    # maior lance que nao da prejuizo nem no pessimista
    lance_seguro = (pess["revenda"] / (1 + reserva) - fixos - pess["manutencao"]) / (1 + com) if revenda else 0

    if cat == "sucata":
        veredito = ("ruim", "Sucata não pode voltar a circular. Só vale para peças.")
    elif not lance:
        veredito = ("info", f"Dê no máximo {brl(max(lance_max, 0))}")
    elif esperado["margem"] >= m_alvo and pess["lucro"] >= 0:
        veredito = ("bom", "Vale a pena nesse lance.")
    elif esperado["lucro"] > 0:
        veredito = ("medio", "Dá lucro no cenário esperado, mas com pouca folga.")
    else:
        veredito = ("ruim", "Prejuízo nesse lance.")

    return {"esperado": esperado, "pessimista": pess, "fator": fator, "fixos": fixos,
            "lance_max": max(lance_max, 0), "lance_seguro": max(lance_seguro, 0),
            "revenda": revenda, "veredito": veredito}

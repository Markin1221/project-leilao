"""Configuracao em config.json (criado na primeira execucao)."""
import json
from pathlib import Path

ARQ = Path(__file__).parent / "config.json"

PADRAO = {
    "patio": 92,                    # Vitoria de Santo Antao - PE
    "comissao_pct": 5,
    "taxas_padrao": 500,            # CHUTE: taxa adm/patio da Copart (confira no edital)
    "documentacao_padrao": 600,     # CHUTE: transferencia + vistoria + laudo
    "frete_local": 150,             # CHUTE: buscar no patio de Vitoria
    "frete_outro_patio": 900,       # CHUTE: moto fisicamente em outro patio (ex.: Eusebio-CE)
    "margem_alvo": 20,
    # revenda = valor de referencia (FIPE) x fator. Venda rapida fica abaixo da FIPE.
    "fator_revenda": {"financiamento": 0.90, "roubo": 0.85, "pequena": 0.80, "media": 0.65, "sucata": 0},
    # quando tem anuncio na OLX-PE: revenda = mediana dos anuncios x fator
    # (anuncio e preco pedido; a venda sai abaixo, e sinistro vende bem pior)
    "fator_sobre_anuncio": {"financiamento": 0.93, "roubo": 0.88, "pequena": 0.82, "media": 0.68, "sucata": 0},
    # manutencao esperada antes de vender (revisao, pneus, relacao, bateria, pecas)
    "manutencao_padrao": {"financiamento": 800, "roubo": 1200, "pequena": 1500, "media": 3500, "sucata": 0},
    "reserva_pct": 10,               # imprevistos, sobre o custo total
    "pessimista_venda_pct": 10,      # cenario ruim: vende 10% mais barato...
    "pessimista_manutencao_x": 2,    # ...e a manutencao sai o dobro
    "navegador_visivel": False,     # mude para true se a Copart bloquear o robo
    "pesquisar_olx": False,         # a OLX bloqueia robos (Cloudflare); desligado
    "telegram_token": "",
    "telegram_chat_id": "",
    "interesses": [
        {"modelo": "CG 160", "ano_min": 2020, "lance_ate": 12000},
    ],
}


def carregar():
    if not ARQ.exists():
        ARQ.write_text(json.dumps(PADRAO, indent=2, ensure_ascii=False), encoding="utf-8")
    dados = json.loads(ARQ.read_text(encoding="utf-8"))
    cfg = {**PADRAO, **dados}
    for k in ("fator_revenda", "fator_sobre_anuncio", "manutencao_padrao"):  # mantem chaves novas mesmo com config antigo
        cfg[k] = {**PADRAO[k], **dados.get(k, {})}
    return cfg

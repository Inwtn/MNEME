"""Fluxo da Binance: trades, livro, derivativos e liquidações. Futuros são só leitura, como atributos de mercado."""

from __future__ import annotations

import json
from datetime import datetime

import httpx
import pandas as pd

SPOT = "https://api.binance.com"
FUTUROS = "https://fapi.binance.com"
WS_SPOT = "wss://stream.binance.com:9443/stream"
WS_FUTUROS = "wss://fstream.binance.com/stream"
LIMITE_TRADES = 1000


def url_spot(pares: list[str]) -> str:
    return WS_SPOT + "?streams=" + "/".join(f"{p.lower()}@aggTrade/{p.lower()}@depth20@1000ms" for p in pares)


def url_futuros(pares: list[str]) -> str:
    return WS_FUTUROS + "?streams=" + "/".join(f"{p.lower()}@forceOrder" for p in pares)


def _ms(valor: int | float) -> pd.Timestamp:
    return pd.Timestamp(int(valor), unit="ms", tz="UTC")


def _trade(id_, preco, quantidade, quando, comprador_passivo, agora: datetime | None, origem: str) -> dict:
    return {"agg_id": int(id_), "preco": float(preco), "quantidade": float(quantidade),
            # Na Binance, `m` verdadeiro quer dizer que o comprador estava parado no livro: quem agrediu foi o vendedor.
            "comprador_agressor": not comprador_passivo, "ocorrido_em": _ms(quando), "recebido_em": agora, "origem": origem}


def trade_do_stream(dados: dict, agora: datetime) -> tuple[str, dict]:
    return dados["s"], _trade(dados["a"], dados["p"], dados["q"], dados["T"], dados["m"], agora, "ws")


def livro_do_stream(par: str, dados: dict, agora: datetime) -> tuple[str, dict]:
    compras = [(float(p), float(q)) for p, q in dados["bids"]]
    vendas = [(float(p), float(q)) for p, q in dados["asks"]]
    if not compras or not vendas:
        raise ValueError("livro vazio")
    melhor_compra, melhor_venda = compras[0][0], vendas[0][0]
    meio = (melhor_compra + melhor_venda) / 2

    def desequilibrio(n: int) -> float:
        c, v = sum(q for _, q in compras[:n]), sum(q for _, q in vendas[:n])
        return (c - v) / (c + v) if c + v else 0.0

    return par, {"update_id": int(dados["lastUpdateId"]), "ocorrido_em": pd.Timestamp(agora), "recebido_em": agora,
                 "melhor_compra": melhor_compra, "melhor_venda": melhor_venda, "spread_bps": (melhor_venda - melhor_compra) / meio * 10_000,
                 "desequilibrio_5": desequilibrio(5), "desequilibrio_20": desequilibrio(20),
                 "profundidade_compra": sum(p * q for p, q in compras), "profundidade_venda": sum(p * q for p, q in vendas),
                 "compras_precos": [p for p, _ in compras], "compras_qtd": [q for _, q in compras],
                 "vendas_precos": [p for p, _ in vendas], "vendas_qtd": [q for _, q in vendas]}


def liquidacao_do_stream(dados: dict, agora: datetime) -> tuple[str, dict]:
    o = dados["o"]
    return o["s"], {"lado": o["S"], "preco": float(o["ap"]) or float(o["p"]), "quantidade": float(o["z"]) or float(o["q"]),
                    "ocorrido_em": _ms(o["T"]), "recebido_em": agora}


def ler_mensagem(mensagem: str | bytes) -> tuple[str, dict] | None:
    """Separa o nome do stream e o conteúdo. Mensagem estranha vira None, para não derrubar a conexão."""
    try:
        corpo = json.loads(mensagem)
        return str(corpo["stream"]), corpo["data"]
    except (ValueError, KeyError, TypeError):
        return None


class FonteFluxo:
    def __init__(self, cliente: httpx.Client | None = None):
        self.cliente = cliente or httpx.Client(timeout=15)

    def _obter(self, url: str, **params):
        resposta = self.cliente.get(url, params=params)
        resposta.raise_for_status()
        return resposta.json()

    def trades_desde(self, par: str, de_id: int, agora: datetime) -> list[dict]:
        """Uma página de trades a partir de `de_id`, para recuperar o que passou durante uma queda."""
        corpo = self._obter(f"{SPOT}/api/v3/aggTrades", symbol=par, fromId=de_id, limit=LIMITE_TRADES)
        return [_trade(t["a"], t["p"], t["q"], t["T"], t["m"], agora, "rest") for t in corpo]

    def derivativos(self, par: str, agora: datetime) -> dict:
        indice = self._obter(f"{FUTUROS}/fapi/v1/premiumIndex", symbol=par)
        aberto = self._obter(f"{FUTUROS}/fapi/v1/openInterest", symbol=par)
        return {"ocorrido_em": _ms(indice["time"]), "recebido_em": agora, "preco_marca": float(indice["markPrice"]),
                "preco_indice": float(indice["indexPrice"]), "funding": float(indice["lastFundingRate"]),
                "proximo_funding_em": _ms(indice["nextFundingTime"]), "open_interest": float(aberto["openInterest"])}

    def funding_historico(self, par: str, inicio: datetime, fim: datetime) -> list[dict]:
        linhas: list[dict] = []
        de = int(pd.Timestamp(inicio).timestamp() * 1000)
        ate = int(pd.Timestamp(fim).timestamp() * 1000)
        while de < ate:
            corpo = self._obter(f"{FUTUROS}/fapi/v1/fundingRate", symbol=par, startTime=de, endTime=ate, limit=1000)
            if not corpo:
                break
            linhas += [{"ocorrido_em": _ms(f["fundingTime"]), "recebido_em": None, "funding": float(f["fundingRate"])} for f in corpo]
            de = int(corpo[-1]["fundingTime"]) + 1
            if len(corpo) < 1000:
                break
        return linhas

    def open_interest_historico(self, par: str, inicio: datetime, fim: datetime) -> list[dict]:
        """Open interest a cada 5 minutos. A Binance guarda só cerca de 30 dias: por isso a coleta contínua importa."""
        linhas: list[dict] = []
        de = int(pd.Timestamp(inicio).timestamp() * 1000)
        ate = int(pd.Timestamp(fim).timestamp() * 1000)
        # A Binance entrega os pontos mais recentes do intervalo: a paginação anda do fim para o começo.
        while de < ate:
            corpo = self._obter(f"{FUTUROS}/futures/data/openInterestHist", symbol=par, period="5m", startTime=de, endTime=ate, limit=500)
            if not corpo:
                break
            linhas += [{"ocorrido_em": _ms(o["timestamp"]), "recebido_em": None, "open_interest": float(o["sumOpenInterest"]),
                        "open_interest_usd": float(o["sumOpenInterestValue"])} for o in corpo]
            ate = min(int(o["timestamp"]) for o in corpo) - 1
            if len(corpo) < 500:
                break
        return linhas

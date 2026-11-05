"""Combinações de metodologias: juntar evidências melhora o que vem depois do sinal, ou só reduz o número de sinais?

Os cortes abaixo foram fixados antes de ver qualquer resultado e não são ajustados: variar aqui contaria como nova tentativa.
Cada parte devolve dois lados (compra e venda). A combinação exige todas as partes do mesmo lado; lados em conflito não geram sinal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import indicadores as ind
from ..leitura import atributos, pivos
from ..metodologias import LADOS, evidencias
from .backtest import apostas_direcao, medir_direcao, placebo_direcao
from .validacao import p_acima_de

PERTO_ATR = 0.5
FVG_ATR = 1.0
RSI_BAIXO, RSI_ALTO = 35.0, 65.0
VOLUME_FORTE = 1.5
RECENTE = 5


def divergencia_rsi(v: pd.DataFrame, rsi: pd.Series, validade: int = RECENTE) -> pd.Series:
    """+1: fundo mais baixo no preço com RSI mais alto. -1: topo mais alto com RSI mais baixo. Só existe depois de o pivô ser confirmado."""
    p = pivos(v, LADOS)
    no_pivo = rsi.shift(LADOS)
    saida = pd.Series(0.0, index=v.index)
    for coluna, sinal, compara in (("fundo", 1.0, np.less), ("topo", -1.0, np.greater)):
        marcas = p[coluna].dropna()
        valores = no_pivo.reindex(marcas.index)
        preco_novo = compara(marcas, marcas.shift())
        rsi_contrario = compara(valores.shift(), valores)
        momentos = marcas.index[preco_novo & rsi_contrario]
        ativo = pd.Series(0.0, index=v.index)
        ativo.loc[momentos] = 1.0
        saida = saida.where(ativo.rolling(validade, min_periods=1).max() == 0, sinal)
    return saida


def _partes(v: pd.DataFrame, a: pd.DataFrame) -> dict[str, tuple[pd.Series, pd.Series]]:
    atr = a["atr_14"].replace(0, np.nan)
    f = a["fechamento"]
    rompeu_alta = (a["rompimento"] > 0).astype(float).rolling(RECENTE, min_periods=1).max() > 0
    rompeu_baixa = (a["rompimento"] < 0).astype(float).rolling(RECENTE, min_periods=1).max() > 0
    # O reteste volta ao nível que foi rompido, guardado no momento do rompimento.
    nivel_alta = a["resistencia"].shift().where(a["rompimento"] > 0).ffill(limit=RECENTE)
    nivel_baixa = a["suporte"].shift().where(a["rompimento"] < 0).ffill(limit=RECENTE)
    agora_rompeu_alta, agora_rompeu_baixa = a["rompimento"] > 0, a["rompimento"] < 0
    volume_forte = a["volume_relativo"] >= VOLUME_FORTE
    divergencia = divergencia_rsi(v, a["rsi_14"])
    return {
        "varredura": (a["liq_varredura"] > 0, a["liq_varredura"] < 0),
        "fvg": (a["fvg_alta_dist"].between(0, FVG_ATR), a["fvg_baixa_dist"].between(0, FVG_ATR)),
        "fib_dourada": ((a["fib_zona_dourada"] == 1) & (a["fib_sentido"] > 0), (a["fib_zona_dourada"] == 1) & (a["fib_sentido"] < 0)),
        "suporte_resistencia": (((f - a["suporte"]) / atr).between(0, PERTO_ATR), ((a["resistencia"] - f) / atr).between(0, PERTO_ATR)),
        "estrutura": (a["estrutura"] > 0, a["estrutura"] < 0),
        "order_block": (a["ob_alta_dist"].between(0, PERTO_ATR), a["ob_baixa_dist"].between(0, PERTO_ATR)),
        "spring": (a["wyckoff_spring"] > 0, a["wyckoff_spring"] < 0),
        "perfil_volume": (a["vp_dist_poc"] < 0, a["vp_dist_poc"] > 0),
        "rsi_extremo": (a["rsi_14"] <= RSI_BAIXO, a["rsi_14"] >= RSI_ALTO),
        "divergencia": (divergencia > 0, divergencia < 0),
        "vwap": (a["distancia_vwap_pct"] > 0, a["distancia_vwap_pct"] < 0),
        "volume": (volume_forte, volume_forte),  # sozinho não tem lado: serve só para confirmar
        "tendencia": (a["tendencia"] == "alta", a["tendencia"] == "baixa"),
        "rompimento": (agora_rompeu_alta, agora_rompeu_baixa),
        "reteste": (rompeu_alta & ~agora_rompeu_alta & (v["minima"] <= nivel_alta) & (f > nivel_alta), rompeu_baixa & ~agora_rompeu_baixa & (v["maxima"] >= nivel_baixa) & (f < nivel_baixa)),
    }


COMBINACOES: dict[str, tuple[str, ...]] = {
    "FVG + varredura": ("fvg", "varredura"),
    "Fibonacci + suporte/resistência": ("fib_dourada", "suporte_resistencia"),
    "Estrutura + order block": ("estrutura", "order_block"),
    "Wyckoff + perfil de volume": ("spring", "perfil_volume"),
    "RSI + divergência + estrutura": ("rsi_extremo", "divergencia", "estrutura"),
    "VWAP + volume + tendência": ("vwap", "volume", "tendencia"),
    "Rompimento + reteste + volume": ("reteste", "volume"),
}


def sinais(v: pd.DataFrame, tempo: str) -> pd.DataFrame:
    """Sinal de cada parte e combinação, por vela de 1 minuto. Vale só no último minuto da vela grande, quando ela já fechou."""
    maior = ind.reamostrar(v.dropna(subset=["fechamento"]), tempo)
    a = atributos(maior)
    a = a.join(evidencias(maior, a))
    partes = _partes(maior, a)
    def lado(compra: pd.Series, venda: pd.Series) -> pd.Series:
        compra, venda = compra.fillna(False).astype(bool), venda.fillna(False).astype(bool)
        return compra.astype(int) - venda.astype(int)  # conflito vira zero
    saida = {nome: lado(*par) for nome, par in partes.items()}
    for nome, itens in COMBINACOES.items():
        compra = pd.concat([partes[i][0].fillna(False).astype(bool) for i in itens], axis=1).all(axis=1)
        venda = pd.concat([partes[i][1].fillna(False).astype(bool) for i in itens], axis=1).all(axis=1)
        saida[nome] = lado(compra, venda)
    tabela = pd.DataFrame(saida)
    tabela.index = tabela.index + pd.Timedelta(tempo) - pd.Timedelta(minutes=1)
    return tabela[tabela.ne(0).any(axis=1)]


def medir_regra(v: pd.DataFrame, sinal: pd.Series, minutos: int, payout: float, sementes: int = 3) -> dict:
    """Mede o que veio depois do sinal, com entrada na abertura seguinte. Inclui placebo e o custo de atrasar um minuto."""
    if not sinal.ne(0).any():
        return {"sinais": 0}
    apostas = apostas_direcao(v, sinal, minutos, payout)
    r = medir_direcao(apostas, payout)
    if r.sinais == 0:
        return {"sinais": 0}
    atraso = medir_direcao(apostas_direcao(v, sinal, minutos, payout, atraso_velas=1), payout)
    alinhado = sinal.reindex(v.index).fillna(0).astype(int)
    placebos = placebo_direcao(v, alinhado, minutos, payout, sementes=sementes)
    return {**r.como_dict(), "p_contra_50": p_acima_de(r.acertos, r.sinais, 0.5), "acerto_com_atraso": atraso.acerto, "placebo": float(np.mean(placebos)) if placebos else None}


def sobreposicao(tabela: pd.DataFrame, nomes: list[str]) -> pd.DataFrame:
    """Fração de sinais em comum entre regras. Regras que disparam juntas são a mesma evidência, não confirmação independente."""
    ativos = tabela[nomes].ne(0)
    uniao = {}
    for a in nomes:
        uniao[a] = {b: float((ativos[a] & ativos[b]).sum() / max((ativos[a] | ativos[b]).sum(), 1)) for b in nomes}
    return pd.DataFrame(uniao)

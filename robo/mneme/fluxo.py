"""Atributos de fluxo por minuto: agressão, tamanho dos negócios e estado do livro. A linha só existe com o minuto fechado."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd


def trades_por_minuto(trades: pd.DataFrame, ate: datetime | None = None) -> pd.DataFrame:
    """Agrega trades no minuto em que aconteceram. `ate` descarta o minuto ainda aberto."""
    if trades.empty:
        return pd.DataFrame()
    t = trades.copy()
    t["minuto"] = t["ocorrido_em"].dt.floor("min")
    if ate is not None:
        t = t[t["minuto"] < pd.Timestamp(ate).floor("min")]
    t["valor"] = t["preco"] * t["quantidade"]
    t["compra"] = t["quantidade"].where(t["comprador_agressor"], 0.0)
    grupos = t.groupby("minuto")
    x = pd.DataFrame({"negocios": grupos.size(), "volume": grupos["quantidade"].sum(), "volume_comprador": grupos["compra"].sum(),
                      "maior_negocio": grupos["quantidade"].max(), "vwap": grupos["valor"].sum() / grupos["quantidade"].sum()})
    x["delta"] = 2 * x["volume_comprador"] - x["volume"]
    x["delta_fracao"] = x["delta"] / x["volume"].replace(0, np.nan)
    x["tamanho_medio"] = x["volume"] / x["negocios"]
    x["concentracao"] = x["maior_negocio"] / x["volume"].replace(0, np.nan)
    return x


def livro_por_minuto(livro: pd.DataFrame, ate: datetime | None = None) -> pd.DataFrame:
    """Resume as fotos do livro de cada minuto, com a última foto e a média. `amostras` baixo indica lacuna."""
    if livro.empty:
        return pd.DataFrame()
    l = livro.copy()
    l["minuto"] = l["ocorrido_em"].dt.floor("min")
    if ate is not None:
        l = l[l["minuto"] < pd.Timestamp(ate).floor("min")]
    grupos = l.sort_values("ocorrido_em").groupby("minuto")
    return pd.DataFrame({"amostras": grupos.size(), "spread_bps_medio": grupos["spread_bps"].mean(), "spread_bps_max": grupos["spread_bps"].max(),
                         "desequilibrio_5_medio": grupos["desequilibrio_5"].mean(), "desequilibrio_5_fim": grupos["desequilibrio_5"].last(),
                         "desequilibrio_20_medio": grupos["desequilibrio_20"].mean(), "profundidade_compra": grupos["profundidade_compra"].mean(),
                         "profundidade_venda": grupos["profundidade_venda"].mean()})


def lacunas_livro(livro: pd.DataFrame, tolerancia_segundos: float = 5) -> list[tuple[pd.Timestamp, float]]:
    """Trechos sem foto do livro: (início, segundos sem dados)."""
    if len(livro) < 2:
        return []
    tempos = livro["ocorrido_em"].sort_values()
    saltos = tempos.diff().dt.total_seconds()
    return [(tempos.iloc[i - 1], float(saltos.iloc[i])) for i in np.flatnonzero(saltos.to_numpy() > tolerancia_segundos)]


def trades_faltando(trades: pd.DataFrame) -> int:
    """Quantos ids de trade faltam entre o primeiro e o último gravados."""
    if trades.empty:
        return 0
    ids = trades["agg_id"].drop_duplicates()
    return int(ids.max() - ids.min() + 1 - len(ids))

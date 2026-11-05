"""Adaptador da Fimathe ao mesmo catálogo e registro dos demais experimentos."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..estrategias.fimathe import RegraFimathe, VelaFimathe, simular

NOME = "Fimathe (canais)"


def configuracao(configuracoes: dict | None, par: str | None = None) -> RegraFimathe | None:
    if not configuracoes:
        return None
    cfg = configuracoes.get("fimathe", configuracoes)
    if cfg.get("schema") != 1 or cfg.get("strategy") != "fimathe":
        return None
    if par is not None and cfg.get("symbol", "").upper() != par.upper():
        return None  # Não usa contrato/custos do ouro em BTC, ETH ou SOL.
    return RegraFimathe.das_configuracoes(cfg.get("parameters", {}))


def preparar(v: pd.DataFrame, regra: RegraFimathe) -> list[VelaFimathe]:
    """Armazém 1m → velas completas do período configurado, sem completar buracos."""
    colunas = ["abertura", "maxima", "minima", "fechamento"]
    if v.empty:
        return []
    if v.index.tz is None or not v.index.is_monotonic_increasing or not v.index.is_unique:
        raise ValueError("Histórico deve ter fuso, sem duplicatas e em ordem crescente.")
    if not ((v.index.second == 0) & (v.index.microsecond == 0)).all():
        raise ValueError("Use velas de 1 minuto alinhadas ao minuto.")
    base = v[colunas]
    if not np.isfinite(base.to_numpy()).all() or (base <= 0).any().any() or (base["maxima"] < base.max(axis=1)).any() or (base["minima"] > base.min(axis=1)).any():
        raise ValueError("Histórico contém preço inválido ou OHLC incoerente.")
    intervalo = pd.Timedelta(minutes=regra.timeframe_minutes)
    grupos = base.resample(intervalo, closed="left", label="left", origin="epoch")
    maior = grupos.agg({"abertura": "first", "maxima": "max", "minima": "min", "fechamento": "last"})
    completa = grupos.count().eq(regra.timeframe_minutes).all(axis=1)
    maior = maior[completa & (maior.index + intervalo <= base.index[-1] + pd.Timedelta(minutes=1))]
    return [VelaFimathe(t.to_pydatetime(), *map(float, linha)) for t, linha in zip(maior.index, maior.itertuples(index=False, name=None))]


def avaliar(v: pd.DataFrame, regra: RegraFimathe) -> dict:
    return simular(preparar(v, regra), regra)


def sinais(v: pd.DataFrame, regra: RegraFimathe | None = None) -> pd.Series:
    resultado = pd.Series(0, index=v.index, dtype="int64")
    if regra is None or v.empty:
        return resultado
    for sinal in avaliar(v, regra)["signals"]:
        # Índice comum é a abertura do último minuto; sinal só fica conhecido ao fechá-lo.
        indice = pd.Timestamp(sinal["time"]) - pd.Timedelta(minutes=1)
        if indice in resultado.index:
            resultado.at[indice] = 1 if sinal["side"] == "buy" else -1
    return resultado


def operacoes(v: pd.DataFrame, regra: RegraFimathe) -> pd.DataFrame:
    """Retorno sobre o patrimônio anterior à entrada, já com lote, spread e custos."""
    linhas = []
    for trade in avaliar(v, regra)["trades"]:
        entrada, saida = pd.Timestamp(trade["opened_at"]), pd.Timestamp(trade["closed_at"])
        linhas.append((entrada, 1 if trade["side"] == "buy" else -1, trade["reason"],
                       int((saida - entrada).total_seconds() / 60), trade["profit"] / trade["equity_before_entry"]))
    return pd.DataFrame(linhas, columns=["quando", "lado", "saida", "velas", "retorno"])

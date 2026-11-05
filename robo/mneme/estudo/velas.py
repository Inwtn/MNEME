"""Atributos do primeiro estudo de velas. A medição fica em `mneme.laboratorio`, sem vazamento entre treino e teste."""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd


def carregar(con: sqlite3.Connection, par: str) -> pd.DataFrame:
    velas = pd.read_sql_query("SELECT abertura_em, abertura, maxima, minima, fechamento, volume, negocios FROM velas "
                              "WHERE par = ? ORDER BY abertura_em", con, params=(par,))
    velas["abertura_em"] = pd.to_datetime(velas["abertura_em"], utc=True)
    return velas.set_index("abertura_em")


def montar(velas: pd.DataFrame, horizonte: int) -> tuple[pd.DataFrame, pd.Series]:
    """Atributos só com o passado de cada vela; o alvo é se o fechamento daqui a `horizonte` minutos é maior."""
    fechamento = velas["fechamento"]
    x = pd.DataFrame(index=velas.index)
    for minutos in (1, 3, 5, 15, 30, 60):
        x[f"retorno_{minutos}"] = fechamento.pct_change(minutos)
    retorno_1 = fechamento.pct_change()
    for minutos in (5, 15, 60):
        x[f"volatilidade_{minutos}"] = retorno_1.rolling(minutos).std()
    x["amplitude"] = (velas["maxima"] - velas["minima"]) / fechamento
    x["corpo"] = (velas["fechamento"] - velas["abertura"]) / fechamento
    x["volume_z"] = (velas["volume"] - velas["volume"].rolling(60).mean()) / velas["volume"].rolling(60).std()
    x["negocios_z"] = (velas["negocios"] - velas["negocios"].rolling(60).mean()) / velas["negocios"].rolling(60).std()
    ganho = retorno_1.clip(lower=0).rolling(14).mean()
    perda = (-retorno_1.clip(upper=0)).rolling(14).mean()
    x["rsi_14"] = 100 - 100 / (1 + ganho / perda.replace(0, np.nan))
    x["distancia_media_60"] = fechamento / fechamento.rolling(60).mean() - 1
    x["hora"] = velas.index.hour
    futuro = fechamento.shift(-horizonte) / fechamento - 1
    y = (futuro > 0).astype(int)
    validas = x.notna().all(axis=1) & futuro.notna() & (futuro != 0)
    return x[validas], y[validas]


def empate(payout: float) -> float:
    """Acerto mínimo para não perder numa aposta que paga `payout` (0,85 = 85%) e perde tudo no erro."""
    return 100 / (1 + payout)

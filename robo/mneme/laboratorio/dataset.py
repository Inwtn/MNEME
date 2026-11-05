"""Dataset de previsão: o que se sabia ao fechar cada vela de 1 minuto, e o que veio depois.

As colunas têm prefixo por família, para medir o que cada tipo de informação acrescenta:
v_ preço e estrutura · m_ metodologias · f_ agressão e negócios · c_ outro mercado · d_ derivativos · t_ relógio · e_ eventos agendados.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import indicadores as ind
from ..leitura import atributos
from ..metodologias import evidencias
from .backtest import continuas

UM_MINUTO = pd.Timedelta(minutes=1)
TEMPOS = ("5min", "15min", "60min")
TEMPOS_METODOLOGIAS = ("15min", "60min")
FAMILIAS = ("v_", "m_", "f_", "c_", "d_", "t_", "e_", "n_")
MAX_MINUTOS_EVENTO = 7 * 24 * 60


def _leitura_em_tempo_maior(v: pd.DataFrame, tempo: str) -> pd.DataFrame:
    """Atributos de um tempo maior, que só valem depois que a vela grande fecha."""
    maior = ind.reamostrar(v.dropna(subset=["fechamento"]), tempo)
    a = atributos(maior)
    f = a["fechamento"]
    atr = a["atr_14"].replace(0, np.nan)
    x = pd.DataFrame(index=a.index)
    for coluna in ("rsi_14", "adx", "di_mais", "di_menos", "bb_posicao", "bb_largura", "atr_pct", "distancia_vwap_pct", "volume_relativo", "largura_percentil",
                   "volatilidade_percentil", "estrutura", "consolidacao", "rompimento", "falso_rompimento", "engolfo", "martelo", "estrela"):
        x[coluna] = a[coluna]
    for periodo in (9, 21, 50):
        x[f"dist_ema_{periodo}"] = (f - a[f"ema_{periodo}"]) / atr
    x["macd_hist"] = a["macd_hist"] / atr
    x["dist_suporte"] = (f - a["suporte"]) / atr
    x["dist_resistencia"] = (a["resistencia"] - f) / atr
    x["tendencia"] = a["tendencia"].map({"alta": 1, "baixa": -1}).fillna(0)
    x = x.add_prefix(f"v_{tempo}_")
    if tempo in TEMPOS_METODOLOGIAS:
        x = x.join(evidencias(maior, a).add_prefix(f"m_{tempo}_"))
    x.index = x.index + pd.Timedelta(tempo) - UM_MINUTO
    return x.reindex(v.index, method="ffill")


def _retornos(serie: pd.Series, prefixo: str) -> pd.DataFrame:
    x = pd.DataFrame(index=serie.index)
    for minutos in (1, 5, 15, 60, 240):
        x[f"{prefixo}retorno_{minutos}"] = serie.pct_change(minutos, fill_method=None)
    variacao = serie.pct_change(fill_method=None)
    for minutos in (15, 60):
        x[f"{prefixo}volatilidade_{minutos}"] = variacao.rolling(minutos).std()
    return x


def construir(v: pd.DataFrame, funding: pd.DataFrame | None = None, referencia: pd.DataFrame | None = None,
              eventos: pd.Series | None = None) -> pd.DataFrame:
    """Uma linha por vela de 1 minuto. Tudo usa apenas o que já estava disponível ao fechar aquela vela."""
    v = continuas(v)
    f = v["fechamento"]
    partes = [_retornos(f, "v_")]
    partes.extend(_leitura_em_tempo_maior(v, tempo) for tempo in TEMPOS)

    fluxo = pd.DataFrame(index=v.index)
    delta = (2 * v["volume_comprador"] - v["volume"])
    for minutos in (1, 5, 15, 60):
        fluxo[f"f_delta_{minutos}"] = delta.rolling(minutos).sum() / v["volume"].rolling(minutos).sum().replace(0, np.nan)
    fluxo["f_volume_rel_60"] = v["volume"] / v["volume"].rolling(60).mean().replace(0, np.nan)
    fluxo["f_negocios_rel_60"] = v["negocios"] / v["negocios"].rolling(60).mean().replace(0, np.nan)
    tamanho = v["volume"] / v["negocios"].replace(0, np.nan)
    fluxo["f_tamanho_rel_60"] = tamanho / tamanho.rolling(60).mean().replace(0, np.nan)
    partes.append(fluxo)

    if referencia is not None:
        partes.append(_retornos(continuas(referencia)["fechamento"].reindex(v.index), "c_"))

    relogio = pd.DataFrame(index=v.index)
    minuto_do_dia = v.index.hour * 60 + v.index.minute
    relogio["t_hora_sen"] = np.sin(2 * np.pi * minuto_do_dia / 1440)
    relogio["t_hora_cos"] = np.cos(2 * np.pi * minuto_do_dia / 1440)
    relogio["t_dia_semana"] = v.index.day_of_week
    relogio["t_ate_funding"] = 480 - (minuto_do_dia % 480)
    partes.append(relogio)

    if funding is not None and not funding.empty:
        taxa = funding.set_index("ocorrido_em")["funding"].sort_index()
        taxa = taxa[~taxa.index.duplicated()]
        d = pd.DataFrame({"d_funding": taxa, "d_funding_delta": taxa.diff(), "d_funding_media_21": taxa.rolling(21).mean(),
                          "d_funding_z_90": (taxa - taxa.rolling(90).mean()) / taxa.rolling(90).std()})
        # Funding de T só se conhece depois de T: a vela aberta em T ainda não pode depender dele antes de fechar, e fecha depois de T.
        partes.append(d.reindex(v.index, method="ffill"))

    if eventos is not None and len(eventos):
        momentos = np.sort(pd.DatetimeIndex(eventos).as_unit("ns").asi8)
        agora = (v.index + UM_MINUTO).as_unit("ns").asi8
        posicao = np.searchsorted(momentos, agora, side="left")
        ate = np.full(len(v), float(MAX_MINUTOS_EVENTO))
        desde = np.full(len(v), float(MAX_MINUTOS_EVENTO))
        tem_proximo = posicao < len(momentos)
        ate[tem_proximo] = (momentos[posicao[tem_proximo]] - agora[tem_proximo]) / 6e10
        tem_anterior = posicao > 0
        desde[tem_anterior] = (agora[tem_anterior] - momentos[posicao[tem_anterior] - 1]) / 6e10
        partes.append(pd.DataFrame({"e_ate_evento": np.minimum(ate, MAX_MINUTOS_EVENTO), "e_desde_evento": np.minimum(desde, MAX_MINUTOS_EVENTO)}, index=v.index))

    return pd.concat(partes, axis=1).replace([np.inf, -np.inf], np.nan)


def alvos(v: pd.DataFrame, horizonte: int) -> pd.DataFrame:
    """O que veio depois de cada vela: a mesma entrada do backtest, na abertura seguinte, com saída `horizonte` minutos depois."""
    v = continuas(v)
    entrada = v["abertura"].shift(-1)
    saida = v["fechamento"].shift(-horizonte)
    retorno = saida / entrada - 1
    passos = np.log(v["fechamento"]).diff()
    futuro = passos.shift(-horizonte)
    ruido = futuro.abs().rolling(horizonte).sum()
    volatilidade = futuro.rolling(horizonte).std()
    return pd.DataFrame({"retorno": retorno, "sobe": (retorno > 0).astype(float).where(retorno.notna() & (retorno != 0)),
                         "vol_futura": np.log(volatilidade.replace(0, np.nan)),
                         "eficiencia": (np.log(saida) - np.log(v["fechamento"])).abs() / ruido.replace(0, np.nan)}, index=v.index)


def amostrar(x: pd.DataFrame, y: pd.DataFrame, horizonte: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Uma linha a cada `horizonte` minutos, para os alvos não se sobreporem. Tira só o aquecimento dos indicadores e o que não tem alvo."""
    grade = x.index[(x.index.hour * 60 + x.index.minute + 1) % horizonte == 0]
    x, y = x.loc[grade], y.loc[grade]
    validas = y["sobe"].notna() & x["v_retorno_240"].notna() & x[f"v_{TEMPOS[-1]}_adx"].notna()
    return x[validas], y[validas]


def colunas_de(x: pd.DataFrame, familias: tuple[str, ...]) -> list[str]:
    return [c for c in x.columns if c.startswith(familias)]

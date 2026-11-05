"""Setups de trading tirados da base de conhecimento (`robo/conhecimento/`), cada um como regra testável.

Cada setup recebe as velas de 1 minuto e devolve, para cada vela, +1 (aposta que sobe), -1 (que desce) ou 0 (nada).
A decisão usa só a vela fechada e o passado; nada olha o futuro.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from functools import partial
from ..laboratorio.fimathe import NOME as NOME_FIMATHE, configuracao as configurar_fimathe, sinais as fimathe


# ---------- indicadores ----------

def ema(serie: pd.Series, periodo: int) -> pd.Series:
    return serie.ewm(span=periodo, adjust=False).mean()


def rsi(fechamento: pd.Series, periodo: int) -> pd.Series:
    variacao = fechamento.diff()
    ganho = variacao.clip(lower=0).ewm(alpha=1 / periodo, adjust=False).mean()
    perda = (-variacao.clip(upper=0)).ewm(alpha=1 / periodo, adjust=False).mean()
    return 100 - 100 / (1 + ganho / perda.replace(0, np.nan))


def vwap_do_dia(velas: pd.DataFrame) -> pd.Series:
    tipico = (velas["maxima"] + velas["minima"] + velas["fechamento"]) / 3
    dia = velas.index.floor("D")
    return (tipico * velas["volume"]).groupby(dia).cumsum() / velas["volume"].groupby(dia).cumsum()


# ---------- padrões de vela ----------

def _corpo(v: pd.DataFrame) -> pd.Series:
    return v["fechamento"] - v["abertura"]


def engolfo(v: pd.DataFrame) -> pd.Series:
    """+1 engolfo de alta, -1 engolfo de baixa."""
    corpo, anterior = _corpo(v), _corpo(v).shift()
    alta = (anterior < 0) & (corpo > 0) & (v["fechamento"] >= v["abertura"].shift()) & (v["abertura"] <= v["fechamento"].shift())
    baixa = (anterior > 0) & (corpo < 0) & (v["fechamento"] <= v["abertura"].shift()) & (v["abertura"] >= v["fechamento"].shift())
    return alta.astype(int) - baixa.astype(int)


def pin_bar(v: pd.DataFrame) -> pd.Series:
    """+1 martelo (pavio de baixo ≥ 2× corpo e ≥ 60% da vela), -1 estrela cadente (o espelho)."""
    amplitude = (v["maxima"] - v["minima"]).replace(0, np.nan)
    corpo = _corpo(v).abs()
    pavio_baixo = v[["abertura", "fechamento"]].min(axis=1) - v["minima"]
    pavio_cima = v["maxima"] - v[["abertura", "fechamento"]].max(axis=1)
    martelo = (pavio_baixo >= 2 * corpo) & (pavio_baixo / amplitude >= 0.6)
    estrela = (pavio_cima >= 2 * corpo) & (pavio_cima / amplitude >= 0.6)
    return martelo.astype(int) - estrela.astype(int)


# ---------- suporte e resistência ----------

def niveis(v: pd.DataFrame, tempo: str = "15min", lados: int = 3) -> tuple[pd.Series, pd.Series]:
    """Último fundo (suporte) e último topo (resistência) de pivôs no tempo maior, só depois de confirmados."""
    maior = v.resample(tempo, label="left", closed="left").agg({"maxima": "max", "minima": "min"}).dropna()
    janela = 2 * lados + 1
    topo = maior["maxima"].where(maior["maxima"] == maior["maxima"].rolling(janela, center=True).max())
    fundo = maior["minima"].where(maior["minima"] == maior["minima"].rolling(janela, center=True).min())
    # Confirmado só quando fecham `lados` velas à direita do pivô, mais a própria vela do tempo maior.
    atraso = pd.Timedelta(tempo) * (lados + 1)
    topo.index = topo.index + atraso
    fundo.index = fundo.index + atraso
    suporte = fundo.dropna().reindex(v.index, method="ffill")
    resistencia = topo.dropna().reindex(v.index, method="ffill")
    return suporte, resistencia


def toque(v: pd.DataFrame, distancia: float = 0.001) -> tuple[pd.Series, pd.Series]:
    """Vela que encostou no suporte (ou na resistência) e fechou do lado certo."""
    suporte, resistencia = niveis(v)
    no_suporte = (v["minima"] <= suporte * (1 + distancia)) & (v["fechamento"] > suporte)
    na_resistencia = (v["maxima"] >= resistencia * (1 - distancia)) & (v["fechamento"] < resistencia)
    return no_suporte, na_resistencia


# ---------- setups ----------

def sr_rejeicao(v: pd.DataFrame) -> pd.Series:
    """Rejeição no nível: martelo ou engolfo de alta no suporte = sobe; estrela ou engolfo de baixa na resistência = desce."""
    no_suporte, na_resistencia = toque(v)
    gatilho = engolfo(v) + pin_bar(v)
    return (no_suporte & (gatilho > 0)).astype(int) - (na_resistencia & (gatilho < 0)).astype(int)


def sr_rejeicao_tendencia(v: pd.DataFrame) -> pd.Series:
    """Rejeição no nível só a favor da EMA 10 (subindo para compra, caindo para venda)."""
    inclinacao = ema(v["fechamento"], 10).diff()
    sinal = sr_rejeicao(v)
    return sinal.where(((sinal > 0) & (inclinacao > 0)) | ((sinal < 0) & (inclinacao < 0)), 0)


def rsi4_80_20(v: pd.DataFrame) -> pd.Series:
    """RSI de 4 períodos saindo da sobrevenda (cruza 20 para cima) = sobe; saindo da sobrecompra (cruza 80 para baixo) = desce."""
    r = rsi(v["fechamento"], 4)
    return ((r.shift() < 20) & (r >= 20)).astype(int) - ((r.shift() > 80) & (r <= 80)).astype(int)


def bollinger_rsi(v: pd.DataFrame) -> pd.Series:
    """Fechou de volta para dentro da banda de Bollinger (20, 2) com RSI 14 em sobrevenda/sobrecompra."""
    media = v["fechamento"].rolling(20).mean()
    desvio = v["fechamento"].rolling(20).std()
    baixa, alta = media - 2 * desvio, media + 2 * desvio
    r = rsi(v["fechamento"], 14)
    volta_de_baixo = (v["fechamento"].shift() < baixa.shift()) & (v["fechamento"] >= baixa) & (r < 35)
    volta_de_cima = (v["fechamento"].shift() > alta.shift()) & (v["fechamento"] <= alta) & (r > 65)
    return volta_de_baixo.astype(int) - volta_de_cima.astype(int)


def ema_9_21_vwap(v: pd.DataFrame) -> pd.Series:
    """EMA 9 cruza a EMA 21 para cima com preço acima da VWAP = sobe; o espelho = desce."""
    rapida, lenta = ema(v["fechamento"], 9), ema(v["fechamento"], 21)
    vwap = vwap_do_dia(v)
    cruza_cima = (rapida.shift() <= lenta.shift()) & (rapida > lenta) & (v["fechamento"] > vwap)
    cruza_baixo = (rapida.shift() >= lenta.shift()) & (rapida < lenta) & (v["fechamento"] < vwap)
    return cruza_cima.astype(int) - cruza_baixo.astype(int)


def so_engolfo(v: pd.DataFrame) -> pd.Series:
    return engolfo(v)


def so_pin_bar(v: pd.DataFrame) -> pd.Series:
    return pin_bar(v)


def tres_velas(v: pd.DataFrame) -> pd.Series:
    """Três velas seguidas da mesma cor = aposta que continua."""
    cor = np.sign(_corpo(v))
    soma = cor.rolling(3).sum()
    return (soma == 3).astype(int) - (soma == -3).astype(int)


def reversao_movimento_forte(v: pd.DataFrame) -> pd.Series:
    """Estudo acadêmico (Bitcoin, 2021): movimento de 1 h acima de 2 desvios tende a voltar. Aposta na volta."""
    retorno_hora = v["fechamento"].pct_change(60)
    desvio = retorno_hora.rolling(24 * 60).std()
    return (retorno_hora < -2 * desvio).astype(int) - (retorno_hora > 2 * desvio).astype(int)


SETUPS: dict[str, Callable[[pd.DataFrame], pd.Series]] = {
    NOME_FIMATHE: fimathe,
    "Rejeição em suporte/resistência": sr_rejeicao,
    "Rejeição em S/R a favor da EMA 10": sr_rejeicao_tendencia,
    "RSI 4 saindo de 80/20": rsi4_80_20,
    "Bollinger + RSI (volta para a banda)": bollinger_rsi,
    "Cruzamento EMA 9/21 + VWAP": ema_9_21_vwap,
    "Engolfo (sozinho)": so_engolfo,
    "Martelo / estrela cadente (sozinho)": so_pin_bar,
    "Três velas da mesma cor (continua)": tres_velas,
    "Reversão após movimento forte de 1 h": reversao_movimento_forte,
}


def setups_configurados(configuracoes: dict | None = None, par: str | None = None) -> dict:
    """Mesmo catálogo; Fimathe só participa com regra completa e contrato do ativo correto."""
    registro = {nome: funcao for nome, funcao in SETUPS.items() if nome != NOME_FIMATHE}
    regra = configurar_fimathe(configuracoes, par)
    if regra is not None:
        registro[NOME_FIMATHE] = partial(fimathe, regra=regra)
    return registro


def medir(v: pd.DataFrame, sinal: pd.Series, minutos: int) -> tuple[int, float, float, float]:
    """Medição antiga e otimista: sobrepõe sinais e entra no fechamento. Para resultados, use `mneme.laboratorio`. Empates não contam.

    Devolve (sinais, acerto %, acerto na 1ª metade %, acerto na 2ª metade %).
    """
    futuro = v["fechamento"].shift(-minutos) - v["fechamento"]
    validos = (sinal != 0) & futuro.notna() & (futuro != 0)
    ganhou = (np.sign(futuro[validos]) == sinal[validos]).to_numpy()
    if len(ganhou) == 0:
        return 0, float("nan"), float("nan"), float("nan")
    metade = len(ganhou) // 2
    return len(ganhou), ganhou.mean() * 100, ganhou[:metade].mean() * 100, ganhou[metade:].mean() * 100

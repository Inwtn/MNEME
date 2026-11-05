"""Backtest por modalidade. O sinal nasce no fechamento de uma vela; a entrada só acontece depois dele, nunca nele."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy import stats

from .validacao import empate, intervalo_wilson, p_acima_de, sharpe

UM_MINUTO = pd.Timedelta(minutes=1)


def continuas(v: pd.DataFrame) -> pd.DataFrame:
    """Coloca uma linha por minuto. Minuto faltando vira vazio, para deslocar por linha ser o mesmo que deslocar no tempo."""
    return v.reindex(pd.date_range(v.index[0], v.index[-1], freq="1min", name=v.index.name))


@dataclass
class ResultadoDirecao:
    sinais: int
    acertos: int
    acerto: float
    limite_inferior: float
    empate: float
    p_valor: float
    retorno_por_aposta: float
    acerto_primeira_metade: float
    acerto_segunda_metade: float

    def como_dict(self) -> dict:
        return asdict(self)


def apostas_direcao(v: pd.DataFrame, sinal: pd.Series, minutos: int, payout: float, atraso_velas: int = 0) -> pd.DataFrame:
    """Opção digital. Entra na abertura da vela seguinte ao sinal (`atraso_velas` a mais) e sai `minutos` depois.

    Uma aposta por vez: sinais durante uma aposta aberta são ignorados, pois não dá para contá-los como casos independentes.
    Empate devolve o valor e não conta.
    """
    v = continuas(v)
    sinal = sinal.reindex(v.index).fillna(0).to_numpy()
    abertura = v["abertura"].to_numpy()
    fechamento = v["fechamento"].to_numpy()
    linhas = []
    livre_em = 0
    for i in np.flatnonzero(sinal):
        entrada = i + 1 + atraso_velas
        saida = entrada + minutos - 1  # fechamento de `saida` é exatamente `minutos` depois da abertura de `entrada`
        if i < livre_em or saida >= len(v):
            continue
        preco_entrada, preco_saida = abertura[entrada], fechamento[saida]
        if np.isnan(preco_entrada) or np.isnan(preco_saida):
            continue
        livre_em = saida + 1
        variacao = (preco_saida - preco_entrada) * sinal[i]
        if variacao == 0:
            continue
        ganhou = variacao > 0
        linhas.append((v.index[i], int(sinal[i]), ganhou, payout if ganhou else -1.0))
    return pd.DataFrame(linhas, columns=["quando", "direcao", "ganhou", "retorno"])


def medir_direcao(apostas: pd.DataFrame, payout: float) -> ResultadoDirecao:
    n = len(apostas)
    referencia = empate(payout)
    if n == 0:
        return ResultadoDirecao(0, 0, float("nan"), float("nan"), referencia, 1.0, float("nan"), float("nan"), float("nan"))
    acertos = int(apostas["ganhou"].sum())
    metade = n // 2
    return ResultadoDirecao(
        sinais=n, acertos=acertos, acerto=acertos / n, limite_inferior=intervalo_wilson(acertos, n)[0], empate=referencia,
        p_valor=p_acima_de(acertos, n, referencia), retorno_por_aposta=float(apostas["retorno"].mean()),
        acerto_primeira_metade=float(apostas["ganhou"].iloc[:metade].mean()) if metade else float("nan"),
        acerto_segunda_metade=float(apostas["ganhou"].iloc[metade:].mean()))


def placebo_direcao(v: pd.DataFrame, sinal: pd.Series, minutos: int, payout: float, sementes: int = 5) -> list[float]:
    """Mantém os mesmos momentos e sorteia a direção. O acerto tem de ficar perto de 50%; caso contrário, o motor está errado."""
    resultados = []
    for semente in range(sementes):
        gerador = np.random.default_rng(semente)
        sorteado = pd.Series(np.where(sinal != 0, gerador.choice([-1, 1], len(sinal)), 0), index=sinal.index)
        apostas = apostas_direcao(v, sorteado, minutos, payout)
        if len(apostas):
            resultados.append(float(apostas["ganhou"].mean()))
    return resultados


@dataclass(frozen=True)
class CustoSpot:
    taxa: float  # por ponta
    slippage: float  # por ponta


@dataclass
class ResultadoPosicao:
    operacoes: int
    acerto: float
    retorno_medio_pct: float
    retorno_total_pct: float
    pior_queda_pct: float
    sharpe_por_operacao: float
    p_valor: float
    saidas: dict

    def como_dict(self) -> dict:
        return asdict(self)


def operacoes_posicao(v: pd.DataFrame, sinal: pd.Series, atr: pd.Series, alvo_atr: float, stop_atr: float, velas_max: int,
                      custo: CustoSpot, so_compra: bool = True) -> pd.DataFrame:
    """Spot com três barreiras: alvo, stop e tempo. Entra na abertura seguinte, com uma posição por vez.

    Se alvo e stop cabem na mesma vela, conta o stop: não dá para saber qual veio primeiro, e o erro fica contra a estratégia.
    Abertura além do stop executa na abertura, que é o preço real da queda.
    """
    v = continuas(v)
    sinal = sinal.reindex(v.index).fillna(0).to_numpy()
    atr = atr.reindex(v.index).to_numpy()
    a, h, l, c = (v[k].to_numpy() for k in ("abertura", "maxima", "minima", "fechamento"))
    linhas = []
    livre_em = 0
    for i in np.flatnonzero(sinal):
        lado = int(sinal[i])
        if i < livre_em or i + 1 >= len(v) or (so_compra and lado < 0) or np.isnan(atr[i]) or np.isnan(a[i + 1]):
            continue
        entrada = a[i + 1]
        alvo, stop = entrada + lado * alvo_atr * atr[i], entrada - lado * stop_atr * atr[i]
        ultimo = min(i + velas_max, len(v) - 1)
        preco, motivo, fim = None, "tempo", ultimo
        for j in range(i + 1, ultimo + 1):
            if np.isnan(h[j]):
                continue
            if (lado > 0 and a[j] <= stop) or (lado < 0 and a[j] >= stop):
                preco, motivo, fim = a[j], "stop", j
                break
            bateu_stop = l[j] <= stop if lado > 0 else h[j] >= stop
            bateu_alvo = h[j] >= alvo if lado > 0 else l[j] <= alvo
            if bateu_stop:
                preco, motivo, fim = stop, "stop", j
                break
            if bateu_alvo:
                preco, motivo, fim = alvo, "alvo", j
                break
        if preco is None:
            preco = c[fim]
            if np.isnan(preco):
                continue
        ida = 1 + lado * (custo.taxa + custo.slippage)
        volta = 1 - lado * (custo.taxa + custo.slippage)
        retorno = lado * ((preco * volta) / (entrada * ida) - 1)
        linhas.append((v.index[i], lado, motivo, fim - i, retorno))
        livre_em = fim + 1
    return pd.DataFrame(linhas, columns=["quando", "lado", "saida", "velas", "retorno"])


def medir_posicao(operacoes: pd.DataFrame) -> ResultadoPosicao:
    if operacoes.empty:
        return ResultadoPosicao(0, float("nan"), float("nan"), 0.0, 0.0, 0.0, 1.0, {})
    r = operacoes["retorno"].to_numpy()
    curva = np.cumprod(1 + r)
    queda = curva / np.maximum.accumulate(np.concatenate([[1.0], curva]))[1:] - 1
    p = float(stats.ttest_1samp(r, 0, alternative="greater").pvalue) if len(r) > 2 and np.std(r) > 0 else 1.0
    return ResultadoPosicao(len(r), float((r > 0).mean()), float(r.mean() * 100), float((curva[-1] - 1) * 100), float(queda.min() * 100),
                            sharpe(r), p, operacoes["saida"].value_counts().to_dict())


def olha_o_futuro(funcao: Callable[[pd.DataFrame], pd.Series], v: pd.DataFrame, cortes: tuple[float, ...] = (0.5, 0.7, 0.9)) -> list[pd.Timestamp]:
    """Devolve as velas cujo sinal muda quando o futuro é escondido. Lista vazia: o sinal é honesto nesses pontos."""
    completo = funcao(v).fillna(0)
    diferentes: list[pd.Timestamp] = []
    for fracao in cortes:
        corte = int(len(v) * fracao)
        parcial = funcao(v.iloc[:corte]).fillna(0)
        comparar = completo.iloc[:corte]
        mudou = comparar[comparar.to_numpy() != parcial.to_numpy()]
        diferentes.extend(mudou.index.tolist())
    return sorted(set(diferentes))

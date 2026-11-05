"""Tenta derrubar um resultado bom antes de acreditar nele. Tudo aqui é pergunta sobre o que veio depois da previsão, fora da amostra.

Previsões confiantes se concentram em certos dias, então o erro é medido sorteando dias inteiros, e não previsões soltas.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from .avaliacao import selecionar_com_passado
from .backtest import continuas
from .previsao import fora_da_amostra
from .validacao import dobras_walk_forward, intervalo_wilson, p_acima_de


def acerto_com_atraso(v: pd.DataFrame, tempos: pd.DatetimeIndex, direcao: np.ndarray, horizonte: int, atraso: int) -> tuple[float, int]:
    """Mesmas previsões, entrando `atraso` minutos depois e mantendo a duração. Empate não conta."""
    v = continuas(v)
    entrada = v["abertura"].shift(-(1 + atraso)).reindex(tempos).to_numpy()
    saida = v["fechamento"].shift(-(horizonte + atraso)).reindex(tempos).to_numpy()
    variacao = (saida - entrada) * direcao
    validas = ~np.isnan(variacao) & (variacao != 0)
    return (float((variacao[validas] > 0).mean()) if validas.any() else float("nan")), int(validas.sum())


def intervalo_por_dias(certos: np.ndarray, tempos: pd.DatetimeIndex, sorteios: int = 2000, semente: int = 0) -> tuple[float, float]:
    """Intervalo de 95% do acerto, sorteando dias inteiros com reposição."""
    tabela = pd.DataFrame({"dia": tempos.floor("D"), "c": certos.astype(float), "n": 1.0}).groupby("dia")[["c", "n"]].sum().to_numpy()
    escolhidos = np.random.default_rng(semente).integers(0, len(tabela), (sorteios, len(tabela)))
    somas = tabela[escolhidos].sum(axis=1)
    taxas = somas[:, 0] / somas[:, 1]
    return float(np.quantile(taxas, 0.025)), float(np.quantile(taxas, 0.975))


def _por_grupo(certos: np.ndarray, grupos: np.ndarray, minimo: int = 30) -> dict[str, dict]:
    saida = {}
    for g in pd.unique(grupos):
        m = grupos == g
        if m.sum() >= minimo:
            saida[str(g)] = {"n": int(m.sum()), "acerto": float(certos[m].mean())}
    return saida


def estressar(x: pd.DataFrame, y: pd.Series, v: pd.DataFrame, horizonte: int, empate: float, criar: Callable, fracao: float = 0.2, dobras: int = 5, embargo: int = 2) -> dict:
    """Reproduz os confiantes com corte do passado e pergunta: sobrevive por período, por dia, por lado, com atraso e com payout menor?"""
    p = fora_da_amostra(criar, x, y, dobras_walk_forward(len(x), dobras, 1, embargo))
    selecao = selecionar_com_passado(np.abs(p.prob - 0.5), p.blocos, fracao)
    tempos = x.index[p.posicoes[selecao]]
    prob, real = p.prob[selecao], p.real[selecao]
    direcao = np.where(prob >= 0.5, 1, -1)
    certos = (prob >= 0.5) == real
    n, acertos = len(certos), int(certos.sum())
    if n == 0:
        return {"confiantes": 0}
    blocos = np.repeat(np.arange(len(p.blocos)), p.blocos)[selecao]
    trimestres = np.asarray(tempos.tz_localize(None).to_period("Q").astype(str))
    por_trimestre = _por_grupo(certos, trimestres)
    ic = intervalo_por_dias(certos, tempos)
    horas = pd.Series(tempos.hour).value_counts(normalize=True)
    volatilidade = x.iloc[p.posicoes[selecao]]["v_60min_volatilidade_percentil"] if "v_60min_volatilidade_percentil" in x else None
    retorno_medio_sempre_alta = float(real.mean())
    return {
        "previsoes": len(p.prob), "confiantes": n, "acerto": acertos / n, "wilson": intervalo_wilson(acertos, n)[0], "ic95_dias": list(ic), "p_contra_empate": p_acima_de(acertos, n, empate),
        "acerto_geral": float(((p.prob >= 0.5) == p.real).mean()), "dias_com_sinal": int(pd.Index(tempos.floor("D")).nunique()),
        "por_dobra": _por_grupo(certos, blocos), "por_trimestre": por_trimestre,
        "trimestres_acima_do_empate": [sum(d["acerto"] > empate for d in por_trimestre.values()), len(por_trimestre)],
        "compra": {"n": int((direcao > 0).sum()), "acerto": float(certos[direcao > 0].mean()) if (direcao > 0).any() else None},
        "venda": {"n": int((direcao < 0).sum()), "acerto": float(certos[direcao < 0].mean()) if (direcao < 0).any() else None},
        "fracao_que_subiu": retorno_medio_sempre_alta, "maior_hora": float(horas.iloc[0]), "horas_com_sinal": int(len(horas)),
        "percentil_vol_medio": float(volatilidade.mean()) if volatilidade is not None else None,
        "com_atraso": {str(a): acerto_com_atraso(v, tempos, direcao, horizonte, a)[0] for a in (1, 2, 5)},
        "expectativa_por_payout": {str(pg): acertos / n * pg - (1 - acertos / n) for pg in (0.75, 0.80, 0.85, 0.90)},
        "ic_acima_do_empate": ic[0] > empate,
    }

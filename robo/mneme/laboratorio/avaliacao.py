"""Avaliação honesta. Todo corte e toda calibração usam só blocos anteriores, e acurácia nunca é confundida com lucro."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression


def inicios_dos_blocos(blocos: list[int]) -> np.ndarray:
    return np.concatenate([[0], np.cumsum(blocos)]).astype(int)


def selecionar_com_passado(valores: np.ndarray, blocos: list[int], fracao: float) -> np.ndarray:
    """Marca os `fracao` maiores valores de cada bloco, com o corte calculado só nos blocos anteriores.

    O primeiro bloco nunca é selecionado, porque antes dele não existe passado para definir o corte. A fração
    real pode diferir de `fracao`, e é assim que deve ser: no mundo real o corte também é escolhido antes.
    """
    inicios = inicios_dos_blocos(blocos)
    marcados = np.zeros(len(valores), dtype=bool)
    for i in range(1, len(blocos)):
        passado = valores[:inicios[i]]
        marcados[inicios[i]:inicios[i + 1]] = valores[inicios[i]:inicios[i + 1]] >= np.quantile(passado, 1 - fracao)
    return marcados


def calibrar_com_passado(prob: np.ndarray, real: np.ndarray, blocos: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """Calibra cada bloco só com os anteriores. Devolve as probabilidades e quais linhas têm calibração válida."""
    inicios = inicios_dos_blocos(blocos)
    saida = prob.astype(float).copy()
    validas = np.zeros(len(prob), dtype=bool)
    for i in range(1, len(blocos)):
        modelo = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(prob[:inicios[i]], real[:inicios[i]])
        saida[inicios[i]:inicios[i + 1]] = modelo.predict(prob[inicios[i]:inicios[i + 1]])
        validas[inicios[i]:inicios[i + 1]] = True
    return saida, validas


def brier(prob: np.ndarray, real: np.ndarray) -> float:
    return float(np.mean((prob - real) ** 2)) if len(prob) else float("nan")


def precisao_e_revocacao(previsto: np.ndarray, real: np.ndarray) -> tuple[float, float]:
    verdadeiros = np.sum(previsto & (real == 1))
    return (float(verdadeiros / previsto.sum()) if previsto.sum() else float("nan"),
            float(verdadeiros / (real == 1).sum()) if (real == 1).sum() else float("nan"))


@dataclass
class Metricas:
    operacoes: int
    acerto: float
    expectativa: float
    fator_de_lucro: float
    resultado_total: float
    pior_queda: float
    sharpe: float
    sortino: float

    def como_dict(self) -> dict:
        return asdict(self)


def metricas(retornos: np.ndarray) -> Metricas:
    """Retornos por operação. Em opção digital, na unidade da aposta: ganho igual ao payout, perda igual a -1."""
    r = np.asarray(retornos, dtype=float)
    if len(r) == 0:
        return Metricas(0, float("nan"), float("nan"), float("nan"), 0.0, 0.0, 0.0, 0.0)
    curva = np.cumsum(r)
    pico = np.maximum.accumulate(np.concatenate([[0.0], curva]))[1:]
    ganhos, perdas = r[r > 0].sum(), -r[r < 0].sum()
    desvio = r.std(ddof=1) if len(r) > 1 else 0.0
    desvio_baixa = np.sqrt(np.mean(np.minimum(r, 0.0) ** 2))
    return Metricas(len(r), float((r > 0).mean()), float(r.mean()), float(ganhos / perdas) if perdas else float("inf"), float(curva[-1]),
                    float((curva - pico).min()), float(r.mean() / desvio) if desvio else 0.0, float(r.mean() / desvio_baixa) if desvio_baixa else 0.0)


def retornos_digitais(ganhou: np.ndarray, payout: float) -> np.ndarray:
    return np.where(ganhou, payout, -1.0)


def por_grupo(retornos: np.ndarray, grupos: np.ndarray) -> dict[str, dict]:
    """Métricas separadas por regime, ativo ou tempo gráfico."""
    return {str(g): metricas(retornos[grupos == g]).como_dict() for g in pd.unique(grupos)}


def regimes(x: pd.DataFrame) -> pd.Series:
    """Regime conhecido no momento da previsão: tendência de 60 min e volatilidade relativa."""
    tendencia = x["v_60min_tendencia"].map({1: "alta", -1: "baixa"}).fillna("sem tendência")
    volatilidade = np.where(x["v_60min_volatilidade_percentil"] >= 0.5, "volátil", "calmo")
    return tendencia + " · " + volatilidade


def separar_selado(indice: pd.DatetimeIndex, selado_desde: pd.Timestamp) -> tuple[np.ndarray, np.ndarray]:
    """Área de desenvolvimento e área selada, que não participa de nenhuma escolha."""
    selado = indice >= selado_desde
    return ~selado, selado

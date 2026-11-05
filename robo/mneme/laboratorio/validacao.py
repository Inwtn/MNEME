"""Validação sem vazamento e estatística para muitos testes.

Referências: López de Prado, Advances in Financial Machine Learning (purga e embargo);
Bailey e López de Prado, The Deflated Sharpe Ratio; Bailey et al., The Probability of Backtest Overfitting.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np
from scipy import stats

GAMA_EULER = 0.5772156649015329


@dataclass(frozen=True)
class Dobra:
    treino: np.ndarray
    teste: np.ndarray


def dobras_walk_forward(n: int, dobras: int = 5, horizonte: int = 1, embargo: int = 0) -> list[Dobra]:
    """Treina no passado e testa à frente. Os últimos `horizonte + embargo` pontos antes do teste ficam fora do treino,
    porque o rótulo deles só se conhece já dentro do período de teste.
    """
    tamanho = n // (dobras + 1)
    if tamanho == 0:
        raise ValueError("Poucos dados para o número de dobras.")
    saida = []
    for i in range(1, dobras + 1):
        inicio = tamanho * i
        fim = n if i == dobras else tamanho * (i + 1)
        corte = max(inicio - horizonte - embargo, 0)
        saida.append(Dobra(np.arange(corte), np.arange(inicio, fim)))
    return saida


def empate(payout: float) -> float:
    """Fração de acerto que zera o resultado de uma aposta que paga `payout` e perde tudo no erro."""
    return 1 / (1 + payout)


def intervalo_wilson(acertos: int, n: int, confianca: float = 0.95) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    z = stats.norm.ppf(1 - (1 - confianca) / 2)
    p = acertos / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    folga = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (float(centro - folga), float(centro + folga))


def p_acima_de(acertos: int, n: int, referencia: float) -> float:
    """Chance de ver esse acerto ou mais por sorte, se o acerto real fosse só `referencia`."""
    if n == 0:
        return 1.0
    return float(stats.binomtest(acertos, n, referencia, alternative="greater").pvalue)


def holm(valores_p: list[float]) -> list[float]:
    """Correção de Holm: ajusta cada p pelo número de testes feitos, sem exigir independência entre eles."""
    n = len(valores_p)
    ajustados = [1.0] * n
    maior = 0.0
    for posicao, indice in enumerate(np.argsort(valores_p)):
        maior = max(maior, min(1.0, (n - posicao) * valores_p[indice]))
        ajustados[indice] = maior
    return ajustados


def sharpe(retornos: np.ndarray) -> float:
    desvio = np.std(retornos, ddof=1) if len(retornos) > 1 else 0.0
    return float(np.mean(retornos) / desvio) if desvio > 0 else 0.0


def sharpe_maximo_esperado(tentativas: int, variancia_sharpes: float) -> float:
    """O melhor Sharpe esperado entre `tentativas` estratégias sem nenhuma vantagem real."""
    if tentativas <= 1:
        return 0.0
    a = stats.norm.ppf(1 - 1 / tentativas)
    b = stats.norm.ppf(1 - 1 / (tentativas * np.e))
    return float(np.sqrt(variancia_sharpes) * ((1 - GAMA_EULER) * a + GAMA_EULER * b))


def sharpe_deflacionado(retornos: np.ndarray, tentativas: int, variancia_sharpes: float) -> float:
    """Probabilidade de o Sharpe real ser maior que o melhor que o acaso daria com esse número de tentativas."""
    n = len(retornos)
    if n < 3 or np.std(retornos) == 0:
        return 0.0
    s = sharpe(retornos)
    assimetria = float(stats.skew(retornos))
    curtose = float(stats.kurtosis(retornos, fisher=False))
    base = sharpe_maximo_esperado(tentativas, variancia_sharpes)
    denominador = np.sqrt(max(1 - assimetria * s + (curtose - 1) / 4 * s * s, 1e-12))
    return float(stats.norm.cdf((s - base) * np.sqrt(n - 1) / denominador))


def prob_sobreajuste(matriz: np.ndarray, blocos: int = 10) -> float:
    """PBO: em quantas divisões a melhor estratégia dentro da amostra fica abaixo da mediana fora dela.

    `matriz` tem uma linha por período e uma coluna por estratégia. Perto de 0,5 ou mais: a escolha do melhor é ruído.
    """
    linhas, colunas = matriz.shape
    if colunas < 2 or linhas < blocos:
        raise ValueError("A PBO precisa de pelo menos 2 estratégias e de um período por bloco.")
    pedacos = np.array_split(np.arange(linhas), blocos)
    abaixo, total = 0, 0
    for dentro in combinations(range(blocos), blocos // 2):
        ind_dentro = np.concatenate([pedacos[i] for i in dentro])
        ind_fora = np.concatenate([pedacos[i] for i in range(blocos) if i not in dentro])
        melhor = int(np.argmax(np.nanmean(matriz[ind_dentro], axis=0)))
        fora = np.nanmean(matriz[ind_fora], axis=0)
        posicao = (fora < fora[melhor]).sum() + 0.5 * ((fora == fora[melhor]).sum() - 1)
        abaixo += posicao / (colunas - 1) <= 0.5
        total += 1
    return abaixo / total

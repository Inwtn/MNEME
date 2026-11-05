"""Estudo de modelos com validação sem vazamento: uma amostra a cada `horizonte` minutos e purga entre treino e teste."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ..estudo.velas import montar
from .validacao import dobras_walk_forward, intervalo_wilson, p_acima_de

MODELOS = {
    "regressão logística": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=500)),
    "gradient boosting": lambda: HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, random_state=0),
}


@dataclass
class ResultadoModelo:
    modelo: str
    previsoes: int
    acerto: float
    limite_inferior: float
    p_valor: float
    acerto_confiante: float
    previsoes_confiantes: int
    p_valor_confiante: float
    acerto_rotulo_embaralhado: float

    def como_dict(self) -> dict:
        return asdict(self)


def preparar(velas: pd.DataFrame, horizonte: int) -> tuple[pd.DataFrame, pd.Series]:
    """Os atributos vêm do estudo original. Fica uma linha a cada `horizonte` minutos, para os alvos não se sobreporem."""
    colunas = ["abertura", "maxima", "minima", "fechamento", "volume", "negocios"]
    x, y = montar(velas[colunas], horizonte)
    return x.iloc[::horizonte], y.iloc[::horizonte]


def avaliar(x: pd.DataFrame, y: pd.Series, referencia: float, dobras: int = 5, embargo: int = 1, confianca: float = 0.2,
            semente: int = 0) -> list[ResultadoModelo]:
    """Como as amostras já não se sobrepõem, o horizonte em linhas é 1; o embargo cobre a memória curta entre vizinhas."""
    divisoes = dobras_walk_forward(len(x), dobras, horizonte=1, embargo=embargo)
    y_embaralhado = pd.Series(np.random.default_rng(semente).permutation(y.to_numpy()), index=y.index)
    saida = []
    for nome, criar in MODELOS.items():
        prob, real, prob_falso, real_falso = [], [], [], []
        for d in divisoes:
            prob.append(criar().fit(x.iloc[d.treino], y.iloc[d.treino]).predict_proba(x.iloc[d.teste])[:, 1])
            real.append(y.iloc[d.teste].to_numpy())
            prob_falso.append(criar().fit(x.iloc[d.treino], y_embaralhado.iloc[d.treino]).predict_proba(x.iloc[d.teste])[:, 1])
            real_falso.append(y_embaralhado.iloc[d.teste].to_numpy())
        p, r = np.concatenate(prob), np.concatenate(real)
        certos = (p >= 0.5) == r
        distancia = np.abs(p - 0.5)
        selecao = distancia >= np.quantile(distancia, 1 - confianca)
        certos_conf = certos[selecao]
        acerto_falso = float((((np.concatenate(prob_falso) >= 0.5) == np.concatenate(real_falso))).mean())
        saida.append(ResultadoModelo(
            modelo=nome, previsoes=len(r), acerto=float(certos.mean()), limite_inferior=intervalo_wilson(int(certos.sum()), len(r))[0],
            p_valor=p_acima_de(int(certos.sum()), len(r), referencia), acerto_confiante=float(certos_conf.mean()),
            previsoes_confiantes=int(selecao.sum()), p_valor_confiante=p_acima_de(int(certos_conf.sum()), int(selecao.sum()), referencia),
            acerto_rotulo_embaralhado=acerto_falso))
    return saida

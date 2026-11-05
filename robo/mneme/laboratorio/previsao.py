"""Modelos de previsão: direção, volatilidade e regime, sempre comparados a uma referência simples."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .avaliacao import brier, calibrar_com_passado, metricas, por_grupo, regimes, retornos_digitais, selecionar_com_passado
from .validacao import Dobra, dobras_walk_forward, intervalo_wilson, p_acima_de


def _lgb_c():
    return lgb.LGBMClassifier(n_estimators=200, learning_rate=0.03, num_leaves=15, min_child_samples=200, subsample=0.7, subsample_freq=1,
                              colsample_bytree=0.7, reg_lambda=5.0, random_state=0, n_jobs=2, verbose=-1)


def _xgb_c():
    # Na perda logística, cada amostra pesa no máximo 0,25: min_child_weight 50 equivale aos 200 exemplos do LightGBM.
    return xgb.XGBClassifier(n_estimators=200, learning_rate=0.03, max_depth=4, min_child_weight=50, subsample=0.7, colsample_bytree=0.7,
                             reg_lambda=5.0, random_state=0, n_jobs=2, tree_method="hist", verbosity=0)


def _logistica():
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=300))


CLASSIFICADORES: dict[str, Callable] = {"logística": _logistica, "LightGBM": _lgb_c, "XGBoost": _xgb_c}


@dataclass
class ResultadoDirecao:
    modelo: str
    previsoes: int
    acerto: float
    auc: float
    limite_inferior: float
    p_valor: float
    acerto_confiante: float
    previsoes_confiantes: int
    p_valor_confiante: float
    erro_calibracao: float
    brier: float
    brier_calibrado: float
    erro_calibracao_calibrado: float
    metricas_confiantes: dict

    def como_dict(self) -> dict:
        return asdict(self)


@dataclass
class Previsoes:
    """Probabilidades fora da amostra, em ordem de tempo. `posicoes` aponta a linha original e `blocos` o tamanho de cada teste."""
    prob: np.ndarray
    real: np.ndarray
    posicoes: np.ndarray
    blocos: list[int]


def erro_calibracao(prob: np.ndarray, real: np.ndarray, faixas: int = 10) -> float:
    """Distância média entre a probabilidade dita e a frequência real, por faixa de probabilidade."""
    cortes = np.quantile(prob, np.linspace(0, 1, faixas + 1))
    grupos = np.clip(np.searchsorted(cortes, prob, side="right") - 1, 0, faixas - 1)
    total = 0.0
    for g in range(faixas):
        m = grupos == g
        if m.any():
            total += m.mean() * abs(prob[m].mean() - real[m].mean())
    return float(total)


def fora_da_amostra(criar: Callable, x: pd.DataFrame, y: pd.Series, dobras: list[Dobra]) -> Previsoes:
    """Probabilidades só em dados que o modelo nunca viu."""
    probs, reais, posicoes, blocos = [], [], [], []
    for d in dobras:
        modelo = criar().fit(x.iloc[d.treino], y.iloc[d.treino])
        probs.append(modelo.predict_proba(x.iloc[d.teste])[:, 1])
        reais.append(y.iloc[d.teste].to_numpy())
        posicoes.append(d.teste)
        blocos.append(len(d.teste))
    return Previsoes(np.concatenate(probs), np.concatenate(reais), np.concatenate(posicoes), blocos)


def medir(nome: str, p: Previsoes, referencia: float, confianca: float = 0.2) -> ResultadoDirecao:
    """O acerto geral usa tudo. "Confiantes" só existem a partir do segundo bloco, com o corte vindo do passado."""
    prob, real = p.prob, p.real
    certos = (prob >= 0.5) == real
    acertos = int(certos.sum())
    selecao = selecionar_com_passado(np.abs(prob - 0.5), p.blocos, confianca)
    conf = certos[selecao]
    auc = float(roc_auc_score(real, prob)) if len(np.unique(real)) > 1 and len(np.unique(prob)) > 1 else 0.5
    calibrada, validas = calibrar_com_passado(prob, real, p.blocos)
    payout = 1 / referencia - 1
    return ResultadoDirecao(
        nome, len(real), float(certos.mean()), auc, intervalo_wilson(acertos, len(real))[0], p_acima_de(acertos, len(real), referencia),
        float(conf.mean()) if len(conf) else float("nan"), int(selecao.sum()), p_acima_de(int(conf.sum()), int(selecao.sum()), referencia),
        erro_calibracao(prob, real), brier(prob, real), brier(calibrada[validas], real[validas]), erro_calibracao(calibrada[validas], real[validas]) if validas.any() else float("nan"),
        metricas(retornos_digitais(conf, payout)).como_dict())


def prever_direcao(x: pd.DataFrame, y: pd.Series, referencia: float, modelos: dict[str, Callable] = CLASSIFICADORES, dobras: int = 5,
                   embargo: int = 2) -> list[ResultadoDirecao]:
    divisoes = dobras_walk_forward(len(x), dobras, 1, embargo)
    return [medir(nome, fora_da_amostra(criar, x, y, divisoes), referencia) for nome, criar in modelos.items()]


def prever_regressao(x: pd.DataFrame, y: pd.Series, referencia: pd.Series, dobras: int = 5, embargo: int = 2) -> dict:
    """Prevê um valor contínuo e compara o erro com o de uma referência simples, como repetir o valor recente."""
    validas = y.notna() & referencia.notna()
    x, y, referencia = x[validas], y[validas], referencia[validas]
    previsto, real, base = [], [], []
    for d in dobras_walk_forward(len(x), dobras, 1, embargo):
        modelo = lgb.LGBMRegressor(n_estimators=200, learning_rate=0.03, num_leaves=15, min_child_samples=200, subsample=0.7, subsample_freq=1,
                                   colsample_bytree=0.7, random_state=0, n_jobs=2, verbose=-1).fit(x.iloc[d.treino], y.iloc[d.treino])
        previsto.append(modelo.predict(x.iloc[d.teste]))
        real.append(y.iloc[d.teste].to_numpy())
        # A referência é ajustada no treino, para a comparação não favorecer o modelo por uma questão de escala.
        ajuste = make_pipeline(Ridge()).fit(referencia.iloc[d.treino].to_frame(), y.iloc[d.treino])
        base.append(ajuste.predict(referencia.iloc[d.teste].to_frame()))
    p, r, b = np.concatenate(previsto), np.concatenate(real), np.concatenate(base)
    erro_modelo, erro_base = float(np.mean((p - r) ** 2)), float(np.mean((b - r) ** 2))
    total = float(np.var(r))
    return {"amostras": len(r), "r2_modelo": 1 - erro_modelo / total, "r2_referencia": 1 - erro_base / total,
            "ganho_sobre_referencia": 1 - erro_modelo / erro_base, "correlacao": float(np.corrcoef(p, r)[0, 1])}


def meta_rotulo(x: pd.DataFrame, ganhou: pd.Series, referencia: float, fracao: float = 0.2, dobras: int = 5, embargo: int = 2) -> dict:
    """Aprende quando confiar numa regra: compara o acerto dela em todos os sinais e só nos que o modelo mais aprova."""
    y = ganhou.astype(int)
    p = fora_da_amostra(_lgb_c, x, y, dobras_walk_forward(len(x), dobras, 1, embargo))
    selecao = selecionar_com_passado(p.prob, p.blocos, fracao)
    escolhidos = p.real[selecao]
    avaliados = p.real[p.blocos[0]:]  # a comparação justa usa só o período em que a seleção podia agir
    payout = 1 / referencia - 1
    retornos = retornos_digitais(escolhidos == 1, payout)
    grupos = regimes(x.iloc[p.posicoes[selecao]]).to_numpy() if {"v_60min_tendencia", "v_60min_volatilidade_percentil"} <= set(x.columns) else None
    return {"sinais": len(avaliados), "acerto_todos": float(avaliados.mean()), "selecionados": int(selecao.sum()),
            "acerto_selecionados": float(escolhidos.mean()) if len(escolhidos) else float("nan"),
            "limite_inferior": intervalo_wilson(int(escolhidos.sum()), len(escolhidos))[0], "p_valor": p_acima_de(int(escolhidos.sum()), len(escolhidos), referencia),
            "auc": float(roc_auc_score(p.real, p.prob)) if len(np.unique(p.real)) > 1 else 0.5,
            "metricas": metricas(retornos).como_dict(), "metricas_todos": metricas(retornos_digitais(avaliados == 1, payout)).como_dict(),
            "por_regime": por_grupo(retornos, grupos) if grupos is not None else {}}


def avaliar_selado(x_dev: pd.DataFrame, y_dev: pd.Series, x_selado: pd.DataFrame, y_selado: pd.Series, referencia: float, fracao: float = 0.2,
                   embargo: int = 2, criar: Callable = _lgb_c) -> dict:
    """Teste final: tudo é escolhido no desenvolvimento, inclusive o corte, e aplicado uma vez em dados nunca usados."""
    fora = fora_da_amostra(criar, x_dev, y_dev, dobras_walk_forward(len(x_dev), 5, 1, embargo))
    corte = float(np.quantile(fora.prob, 1 - fracao))
    modelo = criar().fit(x_dev.iloc[:len(x_dev) - embargo], y_dev.iloc[:len(y_dev) - embargo])
    prob = modelo.predict_proba(x_selado)[:, 1]
    real = y_selado.to_numpy().astype(float)
    selecao = prob >= corte
    escolhidos = real[selecao]
    payout = 1 / referencia - 1
    return {"sinais": len(real), "acerto_todos": float(real.mean()) if len(real) else float("nan"), "corte": corte, "selecionados": int(selecao.sum()),
            "acerto_selecionados": float(escolhidos.mean()) if len(escolhidos) else float("nan"),
            "limite_inferior": intervalo_wilson(int(escolhidos.sum()), len(escolhidos))[0] if len(escolhidos) else float("nan"),
            "p_valor": p_acima_de(int(escolhidos.sum()), len(escolhidos), referencia), "brier": brier(prob, real),
            "metricas": metricas(retornos_digitais(escolhidos == 1, payout)).como_dict(), "metricas_todos": metricas(retornos_digitais(real == 1, payout)).como_dict()}


def importancia_por_familia(modelo: lgb.LGBMClassifier, colunas: list[str]) -> dict[str, float]:
    """Quanto do ganho do modelo veio de cada família de dados."""
    ganho = modelo.booster_.feature_importance(importance_type="gain")
    total = float(ganho.sum()) or 1.0
    familias: dict[str, float] = {}
    for coluna, valor in zip(colunas, ganho):
        familias[coluna[:2]] = familias.get(coluna[:2], 0.0) + float(valor) / total
    return familias


@dataclass
class Artefato:
    caminho: Path
    booster: lgb.Booster
    manifesto: dict

    def prever(self, x: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """Devolve a probabilidade bruta e a calibrada com dados fora da amostra."""
        bruta = self.booster.predict(x[self.manifesto["colunas"]])
        calibracao = self.manifesto["calibracao"]
        return bruta, np.interp(bruta, calibracao["x"], calibracao["y"])


def treinar_artefato(pasta: Path | str, par: str, horizonte: int, x: pd.DataFrame, y: pd.Series, dados: str, commit: str, criar: Callable = _lgb_c,
                     embargo: int = 2) -> Artefato:
    """Treina com tudo e calibra com previsões fora da amostra. O hash permite conferir o artefato ao importar de outra máquina."""
    divisoes = dobras_walk_forward(len(x), 5, 1, embargo)
    fora = fora_da_amostra(criar, x, y, divisoes)
    isotonica = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(fora.prob, fora.real)
    final = criar().fit(x, y)
    identificador = f"{par}-{horizonte}m-{x.index[-1]:%Y%m%d%H%M}"
    destino = Path(pasta) / identificador
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / "modelo.txt"
    final.booster_.save_model(str(arquivo))
    manifesto = {"id": identificador, "par": par, "horizonte": horizonte, "tipo": "direção", "nivel": 2, "dados": dados, "commit": commit,
                 "treino_de": x.index[0].isoformat(), "treino_ate": x.index[-1].isoformat(), "amostras": len(x), "colunas": list(x.columns),
                 "metricas_fora_da_amostra": medir("LightGBM", fora, 0.5).como_dict(),
                 "calibracao": {"x": [float(v) for v in isotonica.X_thresholds_], "y": [float(v) for v in isotonica.y_thresholds_]},
                 "hash": hashlib.sha256(arquivo.read_bytes()).hexdigest()}
    (destino / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=1), encoding="utf-8")
    return Artefato(destino, final.booster_, manifesto)


def carregar_artefato(pasta: Path | str) -> Artefato:
    pasta = Path(pasta)
    manifesto = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    arquivo = pasta / "modelo.txt"
    if hashlib.sha256(arquivo.read_bytes()).hexdigest() != manifesto["hash"]:
        raise ValueError(f"Hash não confere: {pasta}")
    return Artefato(pasta, lgb.Booster(model_file=str(arquivo)), manifesto)

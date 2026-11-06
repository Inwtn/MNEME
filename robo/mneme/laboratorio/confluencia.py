"""Operar quando as técnicas batem: isso funciona mesmo? Compara contagem simples de votos, pesos aprendidos e cada técnica sozinha.

Contar votos trata todas as técnicas como iguais. Pesos aprendidos dão a cada uma o valor que ela mostrou no passado, inclusive negativo.
Tudo fora da amostra, com o corte de confiança vindo só do passado, um minuto de atraso e área selada cortada antes de qualquer cálculo.

    python -m mneme.laboratorio.confluencia
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from ..config import PASTA_DADOS
from ..dados.armazem import ArmazemVelas
from .avaliacao import selecionar_com_passado
from .dataset import alvos
from .horizontes import medir_operacoes, retorno_da_operacao, uma_por_vez
from .previsao import fora_da_amostra
from .registro import Registro, impressao_dos_dados
from .tecnicas import NOMES, todas_as_tecnicas
from .validacao import dobras_walk_forward

SELADO_DESDE = pd.Timestamp("2026-08-01", tz="UTC")
PARES = ("ETHUSDT", "BTCUSDT", "SOLUSDT")
EXPIRACOES = (5, 15)
NIVEIS_DE_VOTOS = (2, 3, 4, 5, 6, 8)
FRACOES = (0.2, 0.1, 0.05)
ATRASO = 1


def _logistica():
    return LogisticRegression(C=0.1, max_iter=500)


def _floresta():
    return lgb.LGBMClassifier(n_estimators=120, learning_rate=0.05, num_leaves=7, min_child_samples=200, subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, random_state=0, n_jobs=2, verbose=-1)


def grade_de_sinais(v: pd.DataFrame, candle: int) -> pd.DataFrame:
    """Uma linha por vela fechada, com o sinal de cada técnica. Vela sem sinal de uma técnica vale zero."""
    s = todas_as_tecnicas(v, f"{candle}min")
    grade = v.index[(v.index.hour * 60 + v.index.minute + 1) % candle == 0]
    return s.reindex(grade).fillna(0).astype("int8")


def medir_direcao_escolhida(v: pd.DataFrame, tempos: pd.DatetimeIndex, direcao: np.ndarray, expiracao: int, custos: dict | None = None, dias: int | None = None) -> dict:
    aceitos = uma_por_vez(tempos, ATRASO, expiracao)
    return medir_operacoes(tempos[aceitos], direcao[aceitos], retorno_da_operacao(v, tempos[aceitos], ATRASO, expiracao), custos, dias)


def por_votos(sinais: pd.DataFrame, v: pd.DataFrame, expiracao: int, niveis: tuple[int, ...] = NIVEIS_DE_VOTOS) -> list[dict]:
    """Saldo de votos: compras menos vendas. Quanto mais técnicas batem, menos sinais; a pergunta é se o acerto sobe de verdade."""
    saldo = sinais.sum(axis=1)
    dias = max(int(pd.Index(sinais.index.floor("D")).nunique()), 1)
    saida = []
    for n in niveis:
        escolhidos = saldo[saldo.abs() >= n]
        if len(escolhidos):
            saida.append({"votos_minimos": n, **medir_direcao_escolhida(v, pd.DatetimeIndex(escolhidos.index), np.sign(escolhidos.to_numpy()).astype(int), expiracao, dias=dias)})
    return saida


def por_pesos(sinais: pd.DataFrame, y: pd.Series, v: pd.DataFrame, expiracao: int, criar: Callable, fracoes: tuple[float, ...] = FRACOES, dobras: int = 5, embargo: int = 2) -> list[dict]:
    """O modelo aprende, só no passado, quanto cada técnica vale, e opera só quando a soma dos sinais dá confiança acima do corte do passado."""
    validas = y.notna()
    x, y = sinais[validas].astype("float32"), y[validas]
    x.columns = [f"t{i}" for i in range(x.shape[1])]  # o LightGBM recusa pontuação em nomes de coluna
    p = fora_da_amostra(criar, x, y, dobras_walk_forward(len(x), dobras, 1, embargo))
    dias = max(int(pd.Index(x.index[p.posicoes].floor("D")).nunique()), 1)
    saida = []
    for fracao in fracoes:
        selecao = selecionar_com_passado(np.abs(p.prob - 0.5), p.blocos, fracao)
        tempos = pd.DatetimeIndex(x.index[p.posicoes[selecao]])
        direcao = np.where(p.prob[selecao] >= 0.5, 1, -1)
        if len(tempos):
            saida.append({"fracao": fracao, **medir_direcao_escolhida(v, tempos, direcao, expiracao, dias=dias)})
    return saida


def pesos_aprendidos(sinais: pd.DataFrame, y: pd.Series) -> dict[str, float]:
    """Quanto cada técnica pesa, para explicar a decisão. Negativo quer dizer que o passado pagou por ir contra ela."""
    validas = y.notna()
    modelo = _logistica().fit(sinais[validas].astype("float32"), y[validas])
    return {NOMES.get(c, c): round(float(p), 4) for c, p in sorted(zip(sinais.columns, modelo.coef_[0]), key=lambda t: -abs(t[1]))}


def main() -> None:
    parser = argparse.ArgumentParser(prog="mneme.laboratorio.confluencia")
    parser.add_argument("--raiz", default=os.getenv("MNEME_DADOS_MERCADO", str(PASTA_DADOS / "mercado")))
    parser.add_argument("--pasta", default=str(PASTA_DADOS / "laboratorio"))
    parser.add_argument("--pares", default=",".join(PARES))
    parser.add_argument("--candle", type=int, default=5)
    args = parser.parse_args()
    pasta = Path(args.pasta)
    armazem, registro = ArmazemVelas(args.raiz), Registro(pasta / "experimentos.jsonl")
    saida = []
    for par in [p.strip().upper() for p in args.pares.split(",") if p.strip()]:
        v = armazem.ler(par)
        v = v[v.index < SELADO_DESDE]
        dados = impressao_dos_dados(v)
        sinais = grade_de_sinais(v, args.candle)
        for h in EXPIRACOES:
            y = alvos(v, h)["sobe"].reindex(sinais.index)
            base = sinais["Bollinger: fora da banda"]
            base = base[base != 0]
            r = {"par": par, "candle": args.candle, "expiracao": h,
                 "so_bollinger": medir_direcao_escolhida(v, pd.DatetimeIndex(base.index), base.to_numpy().astype(int), h, dias=max(int(pd.Index(sinais.index.floor("D")).nunique()), 1)),
                 "votos": por_votos(sinais, v, h), "pesos_logistica": por_pesos(sinais, y, v, h, _logistica), "pesos_arvores": por_pesos(sinais, y, v, h, _floresta), "pesos": pesos_aprendidos(sinais, y)}
            saida.append(r)
            registro.anotar("confluencia", "votos_e_pesos", {"par": par, "candle": args.candle, "expiracao": h}, dados, {k: r[k] for k in ("so_bollinger", "votos", "pesos_logistica", "pesos_arvores")})
            print(f"{par} {h} min pronto", flush=True)
    limpo = json.loads(json.dumps(saida, default=float), parse_constant=lambda _: None)
    (pasta / "confluencia.json").write_text(json.dumps(limpo, ensure_ascii=False, indent=1), encoding="utf-8")
    print("FIM", flush=True)


if __name__ == "__main__":
    main()

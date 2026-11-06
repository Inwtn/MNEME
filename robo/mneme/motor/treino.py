"""Treina os pesos de cada estratégia e mede a evidência na própria modalidade, com área selada cortada antes de qualquer cálculo e um minuto de atraso."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..laboratorio.avaliacao import selecionar_com_passado
from ..laboratorio.confluencia import ATRASO, SELADO_DESDE, _logistica, grade_de_sinais, medir_direcao_escolhida, treinar_pesos
from ..laboratorio.dataset import alvos
from ..laboratorio.horizontes import uma_por_vez
from ..laboratorio.previsao import fora_da_amostra
from ..laboratorio.registro import Registro, impressao_dos_dados
from ..laboratorio.validacao import dobras_walk_forward
from .modalidades import ComStop, Configuracao, Estrategia, amplitude_media, liquidar_stop

# Em velas de 1 minuto, um ano já dá amostra de sobra e cabe na memória da máquina.
MESES_POR_CANDLE = {1: 12}


def selecao_fora_da_amostra(sinais: pd.DataFrame, y: pd.Series, fracao: float, dobras: int = 5, embargo: int = 2) -> tuple[pd.DatetimeIndex, np.ndarray]:
    validas = y.notna()
    x, y = sinais[validas].astype("float32"), y[validas]
    p = fora_da_amostra(_logistica, x, y, dobras_walk_forward(len(x), dobras, 1, embargo))
    selecao = selecionar_com_passado(np.abs(p.prob - 0.5), p.blocos, fracao)
    return pd.DatetimeIndex(x.index[p.posicoes[selecao]]), np.where(p.prob[selecao] >= 0.5, 1, -1)


def medir_com_stop(v: pd.DataFrame, tempos: pd.DatetimeIndex, direcao: np.ndarray, e: Estrategia, m: ComStop) -> dict:
    """Mede o R bruto, sem custo, para o custo ser descontado pela modalidade. `r_por_bps` é quanto cada bps de custo pesa em R nestas operações."""
    if not m.vende:
        tempos, direcao = tempos[direcao == 1], direcao[direcao == 1]
    amplitude = amplitude_media(v, e.candle)
    aceitos = uma_por_vez(tempos, ATRASO, e.expiracao)
    brutos, r_por_bps = [], []
    for t, d in zip(tempos[aceitos], direcao[aceitos]):
        a = amplitude.get(t)
        if a is None or not a > 0:
            continue
        entrada_em = t + pd.Timedelta(minutes=1 + ATRASO)
        r = liquidar_stop(v.loc[entrada_em:entrada_em + pd.Timedelta(minutes=e.expiracao - 1)], entrada_em, e.expiracao, int(d), float(a * m.stop_atr), float(a * m.alvo_atr), 0.0)
        if r is not None:
            brutos.append(r["pnl_bruto"])
            r_por_bps.append(r["preco_entrada"] / (a * m.stop_atr) / 1e4)
    if not brutos:
        return {"operacoes": 0}
    b = np.asarray(brutos)
    custo = np.asarray(r_por_bps) * m.custo_bps
    liquido = b - custo
    return {"operacoes": len(b), "r_bruto": float(b.mean()), "r_por_bps": float(np.mean(r_por_bps)), "r_liquido": float(liquido.mean()), "acerto": float((liquido > 0).mean())}


def treinar_estrategia(e: Estrategia, v: pd.DataFrame, sinais: pd.DataFrame) -> dict:
    y = alvos(v, e.expiracao)["sobe"].reindex(sinais.index)
    modelo = treinar_pesos(sinais, y, fracao=e.fracao)
    tempos, direcao = selecao_fora_da_amostra(sinais, y, e.fracao)
    if isinstance(e.modalidade, ComStop):
        evidencia = medir_com_stop(v, tempos, direcao, e, e.modalidade)
    else:
        evidencia = medir_direcao_escolhida(v, tempos, direcao, e.expiracao, dias=max(int(pd.Index(sinais.index.floor("D")).nunique()), 1))
    return {**modelo, "estrategia": e.nome, "evidencia": evidencia}


def treinar_todas(config: Configuracao, raiz: Path | str, destino: Path | str, registro: Registro, armazem, candles: set[int] | None = None) -> list[dict]:
    """Do candle maior para o menor: os mais caros por último, e cada modelo é gravado assim que fica pronto."""
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    saida = []
    velas: dict[str, pd.DataFrame] = {}
    grades: dict[tuple[str, int], pd.DataFrame] = {}
    estrategias = sorted((e for e in config.estrategias if candles is None or e.candle in candles), key=lambda e: (-e.candle, e.ativo))
    for e in estrategias:
        if e.ativo not in velas:
            velas.clear()
            grades.clear()
            v = armazem.ler(e.ativo)
            velas[e.ativo] = v[v.index < SELADO_DESDE]
        v = velas[e.ativo]
        if v.empty:
            continue
        meses = MESES_POR_CANDLE.get(e.candle)
        recorte = v[v.index >= v.index[-1] - pd.DateOffset(months=meses)] if meses else v
        if (e.ativo, e.candle) not in grades:
            grades[(e.ativo, e.candle)] = grade_de_sinais(recorte, e.candle)
        modelo = treinar_estrategia(e, recorte, grades[(e.ativo, e.candle)])
        (destino / e.arquivo).write_text(json.dumps(modelo, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
        ev = modelo["evidencia"]
        expectativa = e.modalidade.expectativa(ev)
        linha = {"estrategia": e.nome, "mercado": e.mercado, "operacoes": ev.get("operacoes"), "por_dia": ev.get("por_dia"), "acerto": ev.get("acerto"), "ic95_dias": ev.get("ic95_dias"), "expectativa": expectativa}
        saida.append(linha)
        registro.anotar("motor", "evidencia", {"estrategia": e.nome, "fracao": e.fracao}, impressao_dos_dados(recorte), linha)
        print(json.dumps(linha, ensure_ascii=False, default=float), flush=True)
    return saida

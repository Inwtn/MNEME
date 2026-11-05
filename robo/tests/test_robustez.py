"""O teste de estresse derruba o que é ruído ou efeito de poucos dias, e mantém um efeito real plantado."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mneme.laboratorio.previsao import CLASSIFICADORES
from mneme.laboratorio.robustez import acerto_com_atraso, estressar, intervalo_por_dias

EMPATE = 1 / 1.85


def _caso(n=6000, efeito=0.0, semente=0):
    g = np.random.default_rng(semente)
    indice = pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC")
    pista = g.normal(size=n)
    sobe = g.random(n) < 0.5 + efeito * np.tanh(pista)
    x = pd.DataFrame({"pista": pista, "ruido": g.normal(size=n)}, index=indice)
    y = pd.Series(sobe.astype(float), index=indice)
    minutos = pd.date_range(indice[0], periods=n * 15 + 30, freq="1min", tz="UTC")
    f = np.full(len(minutos), 100.0) + np.cumsum(g.normal(0, 0.01, len(minutos)))
    v = pd.DataFrame({"abertura": f, "maxima": f + 0.1, "minima": f - 0.1, "fechamento": f, "volume": 1.0}, index=minutos)
    return x, y, v


def test_efeito_plantado_sobrevive():
    x, y, v = _caso(efeito=0.2)
    r = estressar(x, y, v, 15, EMPATE, CLASSIFICADORES["LightGBM"])
    assert r["acerto"] > 0.6 and r["ic_acima_do_empate"]
    assert r["acerto"] > r["acerto_geral"]  # confiar mais precisa valer alguma coisa
    assert r["trimestres_acima_do_empate"][0] == r["trimestres_acima_do_empate"][1]


def test_ruido_nao_passa():
    x, y, v = _caso(efeito=0.0, semente=1)
    r = estressar(x, y, v, 15, EMPATE, CLASSIFICADORES["LightGBM"])
    assert not r["ic_acima_do_empate"] and abs(r["acerto"] - 0.5) < 0.05


def test_intervalo_por_dias_fica_largo_quando_tudo_vem_de_poucos_dias():
    tempos_espalhados = pd.date_range("2025-01-01", periods=2000, freq="6h", tz="UTC")
    g = np.random.default_rng(0)
    independentes = g.random(2000) < 0.55
    # Mesma média, mas cada dia inteiro acerta ou erra junto.
    dias = pd.Index(tempos_espalhados.floor("D")).unique()
    por_dia = pd.Series(g.random(len(dias)) < 0.55, index=dias)
    juntos = por_dia.reindex(tempos_espalhados.floor("D")).to_numpy()
    a = intervalo_por_dias(independentes, tempos_espalhados)
    b = intervalo_por_dias(juntos, tempos_espalhados)
    assert (b[1] - b[0]) > 1.5 * (a[1] - a[0])


def test_atraso_entra_depois_e_mantem_a_duracao():
    n = 200
    indice = pd.date_range("2025-01-01", periods=n, freq="1min", tz="UTC")
    f = np.arange(n, dtype=float) + 100
    v = pd.DataFrame({"abertura": f, "maxima": f, "minima": f, "fechamento": f + 0.5, "volume": 1.0}, index=indice)
    acerto, validas = acerto_com_atraso(v, indice[[10]], np.array([1]), 15, 1)
    assert acerto == 1.0 and validas == 1


def test_movimento_so_no_primeiro_minuto_some_com_o_atraso():
    n = 100
    indice = pd.date_range("2025-01-01", periods=n, freq="1min", tz="UTC")
    f = np.full(n, 100.0)
    f[11:] = 101.0  # o preço salta só no minuto da entrada, depois fica parado
    v = pd.DataFrame({"abertura": np.concatenate([[100.0], f[:-1]]), "maxima": f, "minima": f, "fechamento": f, "volume": 1.0}, index=indice)
    assert acerto_com_atraso(v, indice[[10]], np.array([1]), 15, 0)[0] == 1.0
    assert acerto_com_atraso(v, indice[[10]], np.array([1]), 15, 2)[1] == 0  # atrasado, nada mudou: empate não conta


def test_sem_confiantes_nao_ha_conclusao():
    x, y, v = _caso(n=6000)
    with pytest.raises(ValueError):
        estressar(x.iloc[:2], y.iloc[:2], v, 15, EMPATE, CLASSIFICADORES["LightGBM"])

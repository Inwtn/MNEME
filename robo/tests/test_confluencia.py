"""Confluência: votos e pesos não olham o futuro, acham o que foi plantado e não inventam vantagem no ruído."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mneme.laboratorio.confluencia import _logistica, grade_de_sinais, pesos_aprendidos, por_pesos, por_votos


def _velas(n=20000, semente=0):
    g = np.random.default_rng(semente)
    f = 100 * np.exp(np.cumsum(g.normal(0, 0.0006, n)))
    a = np.concatenate([[100.0], f[:-1]])
    folga = np.abs(g.normal(0, 0.03, n))
    volume = g.lognormal(3, 1, n)
    return pd.DataFrame({"abertura": a, "maxima": np.maximum(a, f) + folga, "minima": np.minimum(a, f) - folga, "fechamento": f, "volume": volume, "negocios": 10, "volume_comprador": volume / 2},
                        index=pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC", name="abertura_em"))


def test_grade_tem_toda_vela_fechada_e_nao_muda_com_o_futuro():
    v = _velas(12000)
    a, b = grade_de_sinais(v, 5), grade_de_sinais(v.iloc[:9000], 5)
    assert ((a.index.minute + 1) % 5 == 0).all() and len(a) == 12000 // 5
    comum = b.index[:-1]
    pd.testing.assert_frame_equal(a.loc[comum, b.columns], b.loc[comum], check_freq=False)


def _caso(plantado: bool):
    """Velas de 5 min em que, se `plantado`, a técnica A acerta e a B erra a próxima vela. C é ruído."""
    n = 30000
    g = np.random.default_rng(1)
    t = pd.date_range("2026-01-01 00:04", periods=n // 5, freq="5min", tz="UTC")
    a_sinal, b_sinal, c_sinal = g.choice([-1, 0, 1], len(t)), g.choice([-1, 0, 1], len(t)), g.choice([-1, 0, 1], len(t))
    passos = g.normal(0, 0.0005, n)
    if plantado:
        for i, k in enumerate(a_sinal):
            pos = 4 + i * 5
            if k != 0 and pos + 6 < n:
                passos[pos + 2:pos + 6] += 0.0008 * k
    f = 100 * np.exp(np.cumsum(passos))
    a = np.concatenate([[100.0], f[:-1]])
    v = pd.DataFrame({"abertura": a, "maxima": np.maximum(a, f), "minima": np.minimum(a, f), "fechamento": f}, index=pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC"))
    s = pd.DataFrame({"A": a_sinal, "B": -a_sinal, "C": c_sinal}, index=t).astype("int8")
    entrada = v["abertura"].shift(-1).reindex(t)
    saida = v["fechamento"].shift(-5).reindex(t)
    return s, (saida > entrada).astype(float), v


def test_pesos_acham_a_tecnica_boa_e_o_lado_da_ruim():
    s, y, v = _caso(True)
    pesos = pesos_aprendidos(s, y)
    assert pesos["A"] > 0.3 and pesos["B"] < -0.3 and abs(pesos["C"]) < pesos["A"] / 3
    r = por_pesos(s, y, v, 5, _logistica, fracoes=(0.2,))[0]
    assert r["acerto"] > 0.6 and r["ic95_dias"][0] > 0.55


def test_ruido_nao_vira_vantagem():
    s, y, v = _caso(False)
    r = por_pesos(s, y, v, 5, _logistica, fracoes=(0.2,))
    # No ruído a confiança quase não varia e o corte do passado pode não deixar nada passar. Não operar é uma resposta certa.
    assert r == [] or abs(r[0]["acerto"] - 0.5) < 0.05


def test_mais_votos_filtram_mais_e_tecnicas_opostas_se_cancelam():
    s, y, v = _caso(True)
    r = por_votos(s[["A", "C"]], v, 5, (1, 2))
    assert r[0]["operacoes"] > r[1]["operacoes"]
    assert por_votos(s[["A", "B"]], v, 5, (1,)) == []  # A e B sempre discordam: nenhum voto líquido

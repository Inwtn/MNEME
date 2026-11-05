"""Combinações de metodologias: sinais honestos, medidos no que vem depois, sem achar efeito no ruído."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mneme.laboratorio.combinacoes import COMBINACOES, divergencia_rsi, medir_regra, sinais, sobreposicao


def _velas(n=6000, semente=0, escala=0.0008):
    g = np.random.default_rng(semente)
    f = 100 * np.exp(np.cumsum(g.normal(0, escala, n)))
    a = np.concatenate([[100.0], f[:-1]])
    folga = np.abs(g.normal(0, escala, n)) * 100
    volume = g.lognormal(3, 1, n)
    return pd.DataFrame({"abertura": a, "maxima": np.maximum(a, f) + folga, "minima": np.minimum(a, f) - folga, "fechamento": f, "volume": volume, "negocios": 10, "volume_comprador": volume * g.uniform(0.3, 0.7, n)},
                        index=pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC", name="abertura_em"))


@pytest.fixture(scope="module")
def velas():
    return _velas()


@pytest.fixture(scope="module")
def tabela(velas):
    return sinais(velas, "15min")


def test_todas_as_combinacoes_e_partes_existem(tabela):
    assert set(COMBINACOES) <= set(tabela.columns)
    assert {p for itens in COMBINACOES.values() for p in itens} <= set(tabela.columns)


def test_sinal_so_no_ultimo_minuto_da_vela_grande(tabela):
    assert ((tabela.index.minute + 1) % 15 == 0).all()


def test_sinal_nao_olha_o_futuro(velas, tabela):
    for corte in (2500, 4000, 5500):
        parcial = sinais(velas.iloc[:corte], "15min")
        comum = parcial.index.intersection(tabela.index)
        comum = comum[comum < velas.index[corte - 1]]
        assert len(comum) > 10
        # Linhas só com zeros são retiradas das tabelas: compara o que existe nas duas.
        pd.testing.assert_frame_equal(parcial.loc[comum], tabela.loc[comum], check_freq=False)


def test_futuro_diferente_nao_muda_o_sinal_passado(velas):
    outro = velas.copy()
    outro.iloc[5000:, outro.columns.get_loc("fechamento")] *= 1.05
    a, b = sinais(velas, "15min"), sinais(outro, "15min")
    limite = velas.index[4900]
    pd.testing.assert_frame_equal(a[a.index < limite], b[b.index < limite], check_freq=False)


def test_volume_sozinho_nao_tem_lado(tabela):
    assert (tabela["volume"] == 0).all()


def test_combinacao_exige_todas_as_partes_no_mesmo_lado(tabela):
    for nome, itens in COMBINACOES.items():
        lado = tabela[nome]
        for item in itens:
            if item != "volume":
                # Uma parte pode indicar os dois lados e dar zero sozinha, mas nunca o lado oposto ao da combinação.
                assert (tabela.loc[lado != 0, item] != -lado[lado != 0]).all(), (nome, item)


def test_divergencia_de_alta_detectada_depois_do_pivo():
    n = 40
    i = np.arange(n)
    minima = np.minimum(95 + 0.5 * np.abs(i - 10), 90 + 0.5 * np.abs(i - 25))  # dois vales, o segundo mais baixo
    v = pd.DataFrame({"abertura": 101.0, "maxima": 102.0, "minima": minima, "fechamento": 101.0, "volume": 1.0}, index=pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"))
    rsi = pd.Series(50.0, index=v.index)
    rsi.iloc[10], rsi.iloc[25] = 20.0, 35.0  # RSI mais alto no segundo fundo
    d = divergencia_rsi(v, rsi)
    assert (d.iloc[:28] == 0).all()  # o pivô de 25 só se confirma três velas depois
    assert d.iloc[28] > 0


def test_ruido_nao_gera_acerto_acima_do_acaso():
    v = _velas(60_000, semente=3)
    t = sinais(v, "15min")
    regra = "estrutura"
    r = medir_regra(v, t[regra], 15, 0.85)
    assert r["sinais"] > 300 and abs(r["acerto"] - 0.5) < 0.05 and r["p_valor"] > 0.05
    assert abs(r["placebo"] - 0.5) < 0.05


def test_efeito_plantado_e_medido():
    v = _velas(5000, semente=4)
    instantes = v.index[::60][1:-2]
    sinal = pd.Series(1, index=instantes)
    fechamento = v["fechamento"].copy()
    for t in instantes:  # depois de cada sinal, o preço sobe de propósito
        pos = v.index.get_loc(t)
        fechamento.iloc[pos + 15] = v["abertura"].iloc[pos + 1] * 1.01
    plantado = v.assign(fechamento=fechamento)
    r = medir_regra(plantado, sinal, 15, 0.85)
    assert r["acerto"] == 1.0 and r["p_valor"] < 0.01


def test_regra_sem_sinal_nao_gera_conclusao(velas):
    assert medir_regra(velas, pd.Series(0, index=velas.index[:10]), 15, 0.85) == {"sinais": 0}


def test_sobreposicao_mostra_regras_que_sao_a_mesma_evidencia():
    t = pd.DataFrame({"a": [1, 1, 0, 0], "b": [1, 1, 0, 0], "c": [0, 0, 1, -1]})
    s = sobreposicao(t, ["a", "b", "c"])
    assert s.loc["a", "b"] == 1.0 and s.loc["a", "c"] == 0.0

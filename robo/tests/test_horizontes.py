"""Comparação de horizontes: parâmetros independentes, custos reais e área selada fora de tudo."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mneme.laboratorio.dataset import construir, contexto_maior
from mneme.laboratorio.estudo_horizontes import SELADO_DESDE, so_desenvolvimento
from mneme.laboratorio.horizontes import (GRUPOS_DE_ATRIBUTOS, Cenario, alvo_de_amplitude, amostrar_grade, comparar_atributos, custos_do_livro, desequilibrio_do_livro, medir_operacoes, medir_regra_de_movimento,
                                          regra_de_movimento, retorno_da_operacao, medir_multi_tempo, uma_por_vez, validacao_do_cenario)


def _velas(n=3000, semente=0, inicio="2026-01-01"):
    g = np.random.default_rng(semente)
    f = 100 * np.exp(np.cumsum(g.normal(0, 0.0008, n)))
    a = np.concatenate([[100.0], f[:-1]])
    folga = np.abs(g.normal(0, 0.05, n))
    volume = g.lognormal(3, 1, n)
    return pd.DataFrame({"abertura": a, "maxima": np.maximum(a, f) + folga, "minima": np.minimum(a, f) - folga, "fechamento": f, "volume": volume, "negocios": 10, "volume_comprador": volume * g.uniform(0.3, 0.7, n)},
                        index=pd.date_range(inicio, periods=n, freq="1min", tz="UTC", name="abertura_em"))


def test_cenario_separa_candle_previsao_entrada_e_expiracao():
    c = Cenario(candle=1, horizonte=5, atraso=2, expiracao=15)
    assert (c.candle, c.horizonte, c.atraso, c.duracao) == (1, 5, 2, 15)
    assert Cenario(5, 15).duracao == 15  # sem expiração própria, dura o horizonte
    with pytest.raises(ValueError):
        Cenario(0, 5)


def test_purga_cobre_o_horizonte_quando_o_candle_e_menor():
    dobra = validacao_do_cenario(6000, Cenario(1, 60), dobras=5, embargo=2)[0]
    assert dobra.teste[0] - dobra.treino[-1] - 1 == 62
    dobra = validacao_do_cenario(6000, Cenario(15, 15), dobras=5, embargo=2)[0]
    assert dobra.teste[0] - dobra.treino[-1] - 1 == 3


def test_entrada_e_saida_respeitam_atraso_e_expiracao():
    v = _velas(100)
    t = v.index[[10]]
    assert retorno_da_operacao(v, t, 0, 5)[0] == pytest.approx(v["fechamento"].iloc[15] / v["abertura"].iloc[11] - 1)
    assert retorno_da_operacao(v, t, 2, 5)[0] == pytest.approx(v["fechamento"].iloc[17] / v["abertura"].iloc[13] - 1)
    assert retorno_da_operacao(v, t, 0, 1)[0] == pytest.approx(v["fechamento"].iloc[11] / v["abertura"].iloc[11] - 1)


def test_saida_alem_do_corte_nao_vira_resultado():
    v = _velas(100)
    assert np.isnan(retorno_da_operacao(v, v.index[[97]], 0, 5)[0])


def test_uma_operacao_de_cada_vez():
    tempos = pd.date_range("2026-01-01", periods=10, freq="1min", tz="UTC")
    assert uma_por_vez(tempos, 0, 3).tolist() == [True, False, False, False, True, False, False, False, True, False]
    assert uma_por_vez(tempos, 1, 1).sum() == 4


def test_acerto_alto_com_custo_alto_nao_paga():
    tempos = pd.date_range("2026-01-01", periods=400, freq="1h", tz="UTC")
    retorno = np.where(np.arange(400) % 10 < 6, 0.0002, -0.0002)  # 60% de acerto, movimentos de 2 bps
    m = medir_operacoes(tempos, np.ones(400), retorno, {"meio_spread_bps": 0.1, "slippage_bps": 0.1})
    assert m["acerto"] == pytest.approx(0.6)
    assert m["derivativo_liquido_bps"] < 0 and m["spot_liquido_bps"] < 0
    assert m["digital"]["0.85"]["expectativa"] > 0  # na digital, o tamanho do movimento não pesa: só o preço da corretora decide


def test_spot_so_compra():
    tempos = pd.date_range("2026-01-01", periods=100, freq="1h", tz="UTC")
    direcao = np.where(np.arange(100) % 2 == 0, 1, -1)
    retorno = np.where(direcao > 0, 0.01, -0.03)  # as vendas ganham muito, mas no spot não dá para vender
    m = medir_operacoes(tempos, direcao, retorno, {"meio_spread_bps": 0.0, "slippage_bps": 0.0})
    assert m["retorno_compras_bps"] == pytest.approx(100.0)
    assert m["spot_liquido_bps"] == pytest.approx(80.0)
    assert m["derivativo_liquido_bps"] == pytest.approx(200 - 10)


def test_custos_medidos_consumindo_o_livro():
    livro = pd.DataFrame({"ocorrido_em": pd.date_range("2026-01-01", periods=2, freq="1s", tz="UTC"), "melhor_compra": 100.0, "melhor_venda": 100.1, "spread_bps": 10.0,
                          "vendas_precos": [np.array([100.1, 100.2])] * 2, "vendas_qtd": [np.array([5.0, 100.0])] * 2, "compras_precos": [np.array([100.0, 99.9])] * 2, "compras_qtd": [np.array([5.0, 100.0])] * 2})
    c = custos_do_livro(livro, tamanho_usd=1000.0)
    assert c["meio_spread_bps"] == 5.0
    assert c["slippage_bps"] == pytest.approx(5, rel=0.1)  # metade no topo e metade um nível abaixo: meio nível de deslize, cerca de 5 bps
    assert custos_do_livro(pd.DataFrame())["medido"] is False


def test_regra_so_decide_com_o_passado():
    v = _velas(20_000)
    a = regra_de_movimento(v, 5)
    b = regra_de_movimento(v.iloc[:15_000], 5)
    comum = b.index[:-2]
    pd.testing.assert_frame_equal(a.loc[comum], b.loc[comum], check_freq=False)
    assert (a["reversao"] == -a["continuacao"]).all()


def test_reversao_plantada_aparece_e_continuacao_perde():
    n = 40_000
    g = np.random.default_rng(1)
    passos = g.normal(0, 0.0005, n)
    for i in range(10, n - 10, 5):
        passos[i + 1:i + 6] -= 0.5 * passos[i - 4:i + 1].sum() / 5  # cada bloco devolve metade do anterior
    f = 100 * np.exp(np.cumsum(passos))
    a = np.concatenate([[100.0], f[:-1]])
    v = pd.DataFrame({"abertura": a, "maxima": np.maximum(a, f), "minima": np.minimum(a, f), "fechamento": f, "volume": 1.0}, index=pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC"))
    r = medir_regra_de_movimento(v, 5, 5, 0, None)
    assert r["reversao"]["acerto"] > 0.6 > 0.4 > r["continuacao"]["acerto"]


def test_ruido_nao_vira_reversao():
    r = medir_regra_de_movimento(_velas(40_000, semente=2), 5, 5, 0, None)
    assert abs(r["reversao"]["acerto"] - 0.5) < 0.05


def test_alvo_de_amplitude_usa_so_o_futuro_e_referencia_so_o_passado():
    v = _velas(500)
    alvo, referencia = alvo_de_amplitude(v, 1)
    assert referencia.iloc[100] == pytest.approx(np.log((v["maxima"].iloc[100] - v["minima"].iloc[100]) / v["fechamento"].iloc[100]))
    assert alvo.iloc[100] == pytest.approx(np.log((v["maxima"].iloc[101] - v["minima"].iloc[101]) / v["fechamento"].iloc[101]))
    assert alvo.notna().sum() > 400  # em 1 minuto a medida existe, ao contrário do desvio padrão


def test_contexto_maior_so_vale_depois_de_a_vela_fechar():
    v = _velas(5000)
    x = contexto_maior(v, ("240min",))
    p = contexto_maior(v.iloc[:4000], ("240min",))
    comum = p.index[-400:-1]
    pd.testing.assert_frame_equal(x.loc[comum], p.loc[comum], check_freq=False)
    fecha = pd.Timestamp("2026-01-01 03:59", tz="UTC")
    assert x.loc[:fecha - pd.Timedelta(minutes=1)].dropna(how="all").empty  # antes de fechar a primeira vela de 4h, nada
    assert all(c.startswith("x_") for c in x.columns)


def test_area_selada_nunca_entra():
    indice = pd.date_range(SELADO_DESDE - pd.Timedelta(minutes=5), periods=10, freq="1min", tz="UTC")
    t = pd.DataFrame({"a": range(10)}, index=indice)
    assert so_desenvolvimento(t).index.max() < SELADO_DESDE and len(so_desenvolvimento(t)) == 5


def test_grupos_de_atributos_dividem_sem_sobrepor():
    x = construir(_velas(4000))
    for coluna in x.columns:
        donos = [g for g, pertence in GRUPOS_DE_ATRIBUTOS.items() if pertence(coluna)]
        assert len(donos) <= 1, (coluna, donos)
    colunas = {g: [c for c in x.columns if p(c)] for g, p in GRUPOS_DE_ATRIBUTOS.items()}
    for g in ("agressão", "volume", "VWAP e desvios", "momentum e exaustão", "volatilidade curta", "estrutura e liquidez"):
        assert colunas[g], g


def _caso_comparacao(efeito):
    g = np.random.default_rng(0)
    n = 9000
    indice = pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC")
    pista = g.normal(size=n)
    x = pd.DataFrame({"a": g.normal(size=n), "b": pista}, index=indice)
    y = pd.Series((g.random(n) < 0.5 + efeito * np.tanh(pista)).astype(float), index=indice)
    return x, y


def test_grupo_util_e_demonstrado():
    x, y = _caso_comparacao(0.25)
    r = comparar_atributos(x, y, Cenario(15, 15), ["a"], ["a", "b"], sorteios=100)
    assert r["demonstrado"] and r["ganho_auc"] > 0.05


def test_grupo_inutil_nao_e_demonstrado():
    x, y = _caso_comparacao(0.0)
    r = comparar_atributos(x, y, Cenario(15, 15), ["a"], ["a", "b"], sorteios=100)
    assert not r["demonstrado"]


def test_multi_tempo_mede_cada_etapa_e_filtra_cada_vez_mais():
    v = _velas(6000)
    x = construir(v)
    linhas = medir_multi_tempo(x, v, 5, None)
    a_favor = [l for l in linhas if l["sentido"] == "a favor do contexto"]
    assert [l["etapa"] for l in a_favor] == ["só contexto 1h", "+ região 15 min", "+ gatilho 5 min", "+ refino 1 min"]
    assert len(linhas) == 8


def test_livro_com_poucos_dados_nao_gera_conclusao():
    assert desequilibrio_do_livro(pd.DataFrame(), _velas(100)) == {"minutos": 0}

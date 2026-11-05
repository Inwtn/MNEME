"""Entrega 3: validação sem vazamento, backtest e registro."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from mneme.laboratorio.backtest import (CustoSpot, apostas_direcao, medir_direcao, medir_posicao, olha_o_futuro, operacoes_posicao,
                                        placebo_direcao)
from mneme.laboratorio.modelos import avaliar
from mneme.laboratorio.registro import Registro, impressao_dos_dados
from mneme.laboratorio.validacao import (dobras_walk_forward, empate, holm, intervalo_wilson, p_acima_de, prob_sobreajuste, sharpe_deflacionado,
                                         sharpe_maximo_esperado)
from mneme.setups import SETUPS

INICIO = datetime(2026, 1, 1, tzinfo=timezone.utc)
SEM_CUSTO = CustoSpot(0, 0)


def passeio(n=6000, semente=1) -> pd.DataFrame:
    g = np.random.default_rng(semente)
    f = 100 * np.exp(np.cumsum(g.normal(0, 0.001, n)))
    a = np.concatenate([[100.0], f[:-1]])
    folga = np.abs(g.normal(0, 0.0005, n)) * f
    return pd.DataFrame({"abertura": a, "maxima": np.maximum(a, f) + folga, "minima": np.minimum(a, f) - folga, "fechamento": f,
                         "volume": g.uniform(10, 100, n), "negocios": g.integers(1, 50, n)},
                        index=pd.date_range(INICIO, periods=n, freq="1min", tz="UTC", name="abertura_em"))


def velas(precos) -> pd.DataFrame:
    """Cada linha é (abertura, máxima, mínima, fechamento)."""
    return pd.DataFrame(precos, columns=["abertura", "maxima", "minima", "fechamento"],
                        index=pd.date_range(INICIO, periods=len(precos), freq="1min", tz="UTC"), dtype=float)


def plana(n, preco=100.0):
    return [(preco, preco, preco, preco)] * n


def sinal_em(v, posicoes, valor=1):
    s = pd.Series(0, index=v.index)
    s.iloc[list(posicoes)] = valor
    return s


# ---------- dobras ----------

@pytest.mark.parametrize("horizonte,embargo", [(1, 0), (15, 0), (15, 10), (60, 30)])
def test_dobras_deixam_a_folga_e_o_treino_vem_antes(horizonte, embargo):
    for d in dobras_walk_forward(6000, 5, horizonte, embargo):
        assert d.treino.max() + horizonte + embargo < d.teste.min()
        assert not set(d.treino) & set(d.teste)


def test_dobras_cobrem_o_teste_sem_repetir_e_ate_o_fim():
    dobras = dobras_walk_forward(1003, 4, 2, 1)
    testes = np.concatenate([d.teste for d in dobras])
    assert len(testes) == len(set(testes)) and testes.max() == 1002


def test_rotulo_de_treino_nunca_alcanca_o_teste():
    """O rótulo do ponto t usa o preço de t + horizonte; ele não pode cair dentro do período de teste."""
    h = 15
    for d in dobras_walk_forward(5000, 5, h):
        assert d.treino.max() + h < d.teste.min()


def test_poucos_dados_avisa():
    with pytest.raises(ValueError):
        dobras_walk_forward(3, 5)


# ---------- estatística ----------

def test_empate_do_payout():
    assert empate(0.85) == pytest.approx(0.5405, abs=1e-4)
    assert empate(0.70) == pytest.approx(0.5882, abs=1e-4)


def test_wilson_com_valor_conhecido():
    baixo, alto = intervalo_wilson(50, 100)
    assert baixo == pytest.approx(0.4038, abs=1e-3) and alto == pytest.approx(0.5962, abs=1e-3)


def test_amostra_necessaria_do_documento():
    """56% contra 54,05%: com cerca de 1.770 sinais, o limite inferior encosta no empate, como diz a arquitetura."""
    n = 1770
    assert intervalo_wilson(int(n * 0.56), n, confianca=0.90)[0] == pytest.approx(empate(0.85), abs=0.002)


def test_p_valor_cai_com_mais_acertos():
    assert p_acima_de(60, 100, 0.54) > p_acima_de(70, 100, 0.54)
    assert p_acima_de(0, 0, 0.54) == 1.0


def test_holm_ajusta_na_ordem_e_nao_passa_de_um():
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm([0.9, 0.9]) == [1.0, 1.0]


def test_mais_tentativas_exigem_mais():
    assert sharpe_maximo_esperado(1, 1) == 0
    assert sharpe_maximo_esperado(100, 1) > sharpe_maximo_esperado(10, 1) > 0
    r = np.random.default_rng(0).normal(0.05, 1, 2000)
    assert sharpe_deflacionado(r, 1000, 0.01) < sharpe_deflacionado(r, 2, 0.01)


def test_pbo_alta_em_ruido_e_baixa_com_vantagem_real():
    g = np.random.default_rng(0)
    ruido = g.normal(0, 1, (1000, 20))
    assert prob_sobreajuste(ruido) > 0.3
    real = ruido.copy()
    real[:, 0] += 1.0
    assert prob_sobreajuste(real) == 0


# ---------- direção ----------

def test_entrada_e_na_abertura_seguinte_e_saida_no_tempo_certo():
    # O sinal sai na vela 0. Quem entrasse no fechamento dela já teria perdido o salto para 110.
    v = velas([(100, 100, 100, 100), (110, 111, 109, 110), (110, 121, 110, 120), (120, 120, 120, 120)])
    apostas = apostas_direcao(v, sinal_em(v, [0]), 2, 0.85)
    assert len(apostas) == 1
    assert bool(apostas["ganhou"].iloc[0]) is True  # entrou a 110 e saiu a 120
    assert apostas["retorno"].iloc[0] == 0.85


def test_erro_perde_tudo_e_empate_nao_conta():
    v = velas([(100, 100, 100, 100), (100, 100, 90, 90), (90, 90, 90, 90), (90, 90, 90, 90), (90, 90, 90, 90), (90, 90, 90, 90)])
    perdeu = apostas_direcao(v, sinal_em(v, [0]), 1, 0.85)
    assert perdeu["retorno"].iloc[0] == -1.0
    assert apostas_direcao(v, sinal_em(v, [2]), 1, 0.85).empty


def test_uma_aposta_por_vez():
    v = passeio(200)
    apostas = apostas_direcao(v, pd.Series(1, index=v.index), 15, 0.85)
    assert apostas["quando"].diff().dropna().min() >= pd.Timedelta(minutes=15)


def test_lacuna_nos_dados_nao_vira_aposta_errada():
    v = passeio(50).drop(passeio(50).index[10:20])
    apostas = apostas_direcao(v, sinal_em(v, [8]), 5, 0.85)
    assert apostas.empty  # a saída cairia dentro do buraco


def test_atraso_entra_mais_tarde():
    v = velas([(100, 100, 100, 100), (100, 110, 100, 110), (110, 111, 105, 105), (105, 106, 104, 105), (105, 105, 105, 105)])
    assert bool(apostas_direcao(v, sinal_em(v, [0]), 2, 0.85)["ganhou"].iloc[0]) is True
    assert bool(apostas_direcao(v, sinal_em(v, [0]), 2, 0.85, atraso_velas=1)["ganhou"].iloc[0]) is False


def test_medir_direcao_com_valores_conhecidos():
    apostas = pd.DataFrame({"ganhou": [True, True, True, False], "retorno": [0.85, 0.85, 0.85, -1.0]})
    r = medir_direcao(apostas, 0.85)
    assert (r.sinais, r.acertos, r.acerto) == (4, 3, 0.75)
    assert r.retorno_por_aposta == pytest.approx(0.3875)
    assert (r.acerto_primeira_metade, r.acerto_segunda_metade) == (1.0, 0.5)


def test_sem_apostas_nao_quebra():
    assert medir_direcao(pd.DataFrame(columns=["ganhou", "retorno"]), 0.85).sinais == 0


def test_placebo_fica_perto_de_cinquenta():
    v = passeio(30_000)
    sinal = pd.Series(np.random.default_rng(3).choice([0, 1], len(v), p=[0.9, 0.1]), index=v.index)
    assert np.mean(placebo_direcao(v, sinal, 5, 0.85)) == pytest.approx(0.5, abs=0.03)


@pytest.mark.parametrize("semente", [1, 2, 3])
def test_regra_sem_informacao_nao_passa_do_empate(semente):
    """Em passeio aleatório, um setup conhecido não pode parecer vencedor: se parecer, o motor tem vazamento."""
    v = passeio(30_000, semente)
    r = medir_direcao(apostas_direcao(v, SETUPS["Bollinger + RSI (volta para a banda)"](v), 15, 0.85), 0.85)
    assert r.sinais > 50
    assert r.p_valor > 0.01


def test_sinal_que_ve_o_futuro_e_pego_pelo_motor_e_pelo_detector():
    v = passeio(5000)

    def trapaca(x):
        return np.sign(x["fechamento"].shift(-5) - x["fechamento"]).fillna(0).astype(int)

    # Com a entrada na abertura seguinte, olhar 5 velas à frente rende acerto irreal.
    assert medir_direcao(apostas_direcao(v, trapaca(v), 5, 0.85), 0.85).acerto > 0.7
    assert olha_o_futuro(trapaca, v)


@pytest.mark.parametrize("nome", list(SETUPS))
def test_nenhum_setup_olha_o_futuro(nome):
    assert olha_o_futuro(SETUPS[nome], passeio(6000)) == []


# ---------- spot com três barreiras ----------

ATR = 1.0


def _op(v, entrada_em=0, **kw):
    atr = pd.Series(ATR, index=v.index)
    return operacoes_posicao(v, sinal_em(v, [entrada_em]), atr, kw.get("alvo", 2), kw.get("stop", 2), kw.get("velas", 5), kw.get("custo", SEM_CUSTO))


def test_sai_no_alvo():
    v = velas(plana(1) + [(100, 100.5, 99.5, 100), (100, 102.5, 100, 102)] + plana(3, 102))
    o = _op(v)
    assert o["saida"].iloc[0] == "alvo" and o["retorno"].iloc[0] == pytest.approx(0.02)


def test_sai_no_stop():
    v = velas(plana(1) + [(100, 100.5, 97, 98)] + plana(3, 98))
    o = _op(v)
    assert o["saida"].iloc[0] == "stop" and o["retorno"].iloc[0] == pytest.approx(-0.02)


def test_alvo_e_stop_na_mesma_vela_conta_o_stop():
    v = velas(plana(1) + [(100, 103, 97, 100)] + plana(3))
    assert _op(v)["saida"].iloc[0] == "stop"


def test_abertura_alem_do_stop_executa_na_abertura():
    v = velas(plana(1) + [(100, 100, 100, 100), (90, 91, 89, 90)] + plana(3, 90))
    o = _op(v)
    assert o["saida"].iloc[0] == "stop" and o["retorno"].iloc[0] == pytest.approx(-0.10)


def test_sai_por_tempo():
    v = velas(plana(1) + [(100, 100.5, 99.5, 100.5)] * 8)
    o = _op(v, velas=3)
    assert o["saida"].iloc[0] == "tempo" and o["velas"].iloc[0] == 3 and o["retorno"].iloc[0] == pytest.approx(0.005)


def test_custos_entram_nas_duas_pontas():
    v = velas(plana(1) + [(100, 100.5, 99.5, 100)] * 8)
    o = _op(v, velas=3, custo=CustoSpot(0.001, 0.0005))
    assert o["retorno"].iloc[0] == pytest.approx(0.9985 / 1.0015 - 1)


def test_uma_posicao_por_vez_e_so_compra():
    v = passeio(300)
    s = pd.Series(1, index=v.index)
    ops = operacoes_posicao(v, s, pd.Series(1.0, index=v.index), 2, 2, 10, SEM_CUSTO)
    fins = ops["quando"] + pd.to_timedelta(ops["velas"], unit="min")
    assert (ops["quando"].iloc[1:].to_numpy() > fins.iloc[:-1].to_numpy()).all()
    assert operacoes_posicao(v, -s, pd.Series(1.0, index=v.index), 2, 2, 10, SEM_CUSTO).empty


def test_medir_posicao_calcula_queda():
    o = pd.DataFrame({"retorno": [0.1, -0.5, 0.2], "saida": ["alvo", "stop", "alvo"]})
    r = medir_posicao(o)
    assert r.operacoes == 3 and r.pior_queda_pct == pytest.approx(-50)
    assert r.saidas == {"alvo": 2, "stop": 1}
    assert medir_posicao(pd.DataFrame(columns=["retorno", "saida"])).operacoes == 0


# ---------- modelos ----------

def test_modelo_em_ruido_fica_perto_de_cinquenta():
    g = np.random.default_rng(0)
    x = pd.DataFrame(g.normal(size=(6000, 5)), columns=list("abcde"))
    y = pd.Series(g.integers(0, 2, 6000))
    for r in avaliar(x, y, 0.5405):
        assert r.acerto == pytest.approx(0.5, abs=0.03)
        assert r.acerto_rotulo_embaralhado == pytest.approx(0.5, abs=0.03)
        assert r.p_valor > 0.5


def test_modelo_acha_sinal_real_e_o_rotulo_embaralhado_nao():
    g = np.random.default_rng(1)
    x = pd.DataFrame(g.normal(size=(6000, 3)), columns=list("abc"))
    y = pd.Series((x["a"] + g.normal(0, 0.5, 6000) > 0).astype(int))
    for r in avaliar(x, y, 0.5405):
        assert r.acerto > 0.8
        assert r.acerto_rotulo_embaralhado == pytest.approx(0.5, abs=0.04)


# ---------- registro ----------

def test_registro_anota_e_conta_cada_combinacao_uma_vez(tmp_path):
    r = Registro(tmp_path / "x" / "e.jsonl", commit="abc")
    r.anotar("f", "a", {"par": "BTC"}, "d1", {"acerto": 0.5})
    r.anotar("f", "a", {"par": "BTC"}, "d1", {"acerto": 0.5})
    r.anotar("f", "a", {"par": "ETH"}, "d1", {"acerto": 0.4})
    r.anotar("g", "b", {}, "d1", {})
    assert r.tentativas("f") == 2 and len(r.todos()) == 4
    assert r.todos("g")[0]["commit"] == "abc"


def test_registro_guarda_tentativa_ruim_para_sempre(tmp_path):
    r = Registro(tmp_path / "e.jsonl", commit="abc")
    r.anotar("f", "ruim", {}, "d", {"acerto": 0.1})
    assert Registro(tmp_path / "e.jsonl", commit="def").tentativas("f") == 1


def test_impressao_muda_com_os_dados():
    v = passeio(100)
    alterado = v.copy()
    alterado.iloc[50, 3] *= 1.01
    assert impressao_dos_dados(v) == impressao_dos_dados(v.copy()) != impressao_dos_dados(alterado)

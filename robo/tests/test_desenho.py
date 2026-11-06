"""Desenhos só com o que existia no instante, e técnicas medidas sem olhar o futuro."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mneme.desenho import agrupar_niveis, desenhar, melhor_linha, svg_do_desenho
from mneme.laboratorio.tecnicas import ombro_cabeca_ombro, resumir, rompimento_de_triangulo, todas_as_tecnicas
from mneme.leitura import atributos


def _velas(n=20000, semente=0):
    g = np.random.default_rng(semente)
    f = 100 * np.exp(np.cumsum(g.normal(0, 0.0008, n)))
    a = np.concatenate([[100.0], f[:-1]])
    folga = np.abs(g.normal(0, 0.05, n))
    volume = g.lognormal(3, 1, n)
    return pd.DataFrame({"abertura": a, "maxima": np.maximum(a, f) + folga, "minima": np.minimum(a, f) - folga, "fechamento": f, "volume": volume, "negocios": 10, "volume_comprador": volume / 2},
                        index=pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC", name="abertura_em"))


def test_pivos_proximos_viram_um_nivel_e_um_toque_nao_faz_nivel():
    t = pd.date_range("2026-01-01", periods=4, freq="1h", tz="UTC")
    niveis = agrupar_niveis(pd.Series([100.0, 100.3, 120.0, 90.0], index=t), atr=1.0, atual=110.0)
    assert len(niveis) == 1 and niveis[0].tipo == "suporte" and niveis[0].toques == 2 and abs(niveis[0].preco - 100.15) < 1e-9


def test_nivel_acima_do_preco_e_resistencia():
    t = pd.date_range("2026-01-01", periods=2, freq="1h", tz="UTC")
    assert agrupar_niveis(pd.Series([100.0, 100.2], index=t), 1.0, 90.0)[0].tipo == "resistencia"


def test_lta_liga_fundos_crescentes_e_conta_os_toques():
    t = pd.date_range("2026-01-01", periods=100, freq="15min", tz="UTC")
    fechamentos = pd.Series(100 + 0.1 * np.arange(100) + 2, index=t)
    fundos = pd.Series([100.0 + 0.1 * i for i in (10, 40, 70)], index=t[[10, 40, 70]])
    l = melhor_linha(fundos, fechamentos, atr=1.0, sobe=True)
    assert l.tipo == "LTA" and l.toques == 3 and abs(l.preco_fim - (100 + 0.1 * 99)) < 1e-9


def test_linha_rompida_por_fechamentos_nao_vale():
    t = pd.date_range("2026-01-01", periods=100, freq="15min", tz="UTC")
    fechamentos = pd.Series(np.concatenate([np.full(60, 110.0), np.full(40, 90.0)]), index=t)
    fundos = pd.Series([100.0, 103.0], index=t[[10, 40]])
    assert melhor_linha(fundos, fechamentos, atr=1.0, sobe=True) is None


def test_ltb_precisa_cair():
    t = pd.date_range("2026-01-01", periods=50, freq="15min", tz="UTC")
    fechamentos = pd.Series(np.full(50, 90.0), index=t)
    assert melhor_linha(pd.Series([100.0, 95.0], index=t[[5, 30]]), fechamentos, 1.0, sobe=False).tipo == "LTB"
    assert melhor_linha(pd.Series([95.0, 100.0], index=t[[5, 30]]), fechamentos, 1.0, sobe=False) is None


def test_desenho_nao_muda_com_o_futuro():
    v = _velas()
    corte = v.index[15_000 - 1]  # fim exato de uma vela de 15 min
    a = desenhar(v.iloc[:15_000], "X", "15min")
    outro = v.copy()
    outro.iloc[15_000:, outro.columns.get_loc("fechamento")] *= 1.3
    b = desenhar(outro.iloc[:15_000], "X", "15min")
    assert a == b
    assert pd.Timestamp(a.ate) <= corte


def test_vela_ainda_aberta_nao_entra():
    v = _velas()
    d = desenhar(v.iloc[:15_007], "X", "15min")  # sete minutos dentro de uma vela de 15
    assert pd.Timestamp(d.ate) + pd.Timedelta(minutes=15) <= v.index[15_006] + pd.Timedelta(minutes=1)


def test_grafico_tem_velas_e_linhas_e_escapa_texto():
    v = _velas()
    d = desenhar(v, "<X>", "15min")
    svg = svg_do_desenho(v, d)
    assert svg.startswith("<svg") and svg.endswith("</svg>") and "&lt;X&gt;" in svg and svg.count("<rect") > 100


def _oco(invertido=False):
    picos = [(20, 110.0), (40, 100.0), (60, 120.0), (80, 100.0), (100, 110.0)]
    x = np.arange(160)
    y = np.interp(x, [0] + [p for p, _ in picos] + [130, 159], [100.0] + [q for _, q in picos] + [90.0, 90.0])
    if invertido:
        y = 200 - y
    t = pd.date_range("2026-01-01", periods=160, freq="15min", tz="UTC")
    a = np.concatenate([[y[0]], y[:-1]])
    return pd.DataFrame({"abertura": a, "maxima": np.maximum(a, y) + 0.01, "minima": np.minimum(a, y) - 0.01, "fechamento": y, "volume": 1.0, "negocios": 1, "volume_comprador": 0.5}, index=t)


def test_oco_so_dispara_ao_perder_a_linha_de_pescoco():
    v = _oco()
    s = ombro_cabeca_ombro(v, atributos(v).assign(atr_14=10.0))
    datas = s[s != 0]
    assert len(datas) == 1 and datas.iloc[0] == -1
    assert v["fechamento"].loc[datas.index[0]] < 100.0  # abaixo da linha de pescoço
    assert v.index.get_loc(datas.index[0]) > 100


def test_oco_invertido_compra():
    v = _oco(True)
    s = ombro_cabeca_ombro(v, atributos(v).assign(atr_14=10.0))
    assert (s[s != 0] == 1).all() and (s != 0).sum() == 1


def test_triangulo_so_conta_com_linhas_convergindo():
    e = pd.DataFrame({"lt_alta_inclinacao": [1.0, 1.0, -1.0, -1.0], "lt_baixa_inclinacao": [-1.0, -1.0, -1.0, -1.0], "lt_baixa_dist": [-0.5, 0.5, -0.5, 0.5], "lt_alta_dist": [0.5, 0.5, 0.5, 0.5]})
    assert rompimento_de_triangulo(e).tolist() == [0, 1, 0, 0]


def test_tecnicas_nao_olham_o_futuro():
    v = _velas(12_000)
    a, b = todas_as_tecnicas(v, "15min"), todas_as_tecnicas(v.iloc[:9000], "15min")
    comum = b.index[b.index < v.index[8999]].intersection(a.index)
    assert len(comum) > 50
    pd.testing.assert_frame_equal(a.loc[comum, b.columns], b.loc[comum], check_freq=False)
    assert ((a.index.minute + 1) % 15 == 0).all()


def test_resumo_ignora_pouca_amostra_e_ordena():
    linhas = [{"tecnica": "A", "sinais": 200, "acertos": 120, "acerto": 0.6, "limite_inferior": 0.55, "par": "X", "tempo": "15min", "horizonte": 15},
              {"tecnica": "B", "sinais": 200, "acertos": 90, "acerto": 0.45, "limite_inferior": 0.4, "par": "X", "tempo": "15min", "horizonte": 15},
              {"tecnica": "C", "sinais": 5, "acertos": 5, "acerto": 1.0, "limite_inferior": 0.5, "par": "X", "tempo": "15min", "horizonte": 15}]
    r = resumir(linhas, 0.54)
    assert [t["tecnica"] for t in r] == ["A", "B"]

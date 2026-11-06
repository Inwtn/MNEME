"""Carteira simulada: grava antes do resultado, não repete, não decide com dado velho e o saldo confere."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from mneme.carteira import ESTRATEGIA_MODELO, Carteira, placar, sinais_do_modelo, ultima_vela_fechada
from mneme.dados.armazem import ArmazemVelas
from mneme.dados.eventos import ArmazemEventos

INICIO = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _velas(n=8000, semente=0):
    g = np.random.default_rng(semente)
    f = 100 * np.exp(np.cumsum(g.normal(0, 0.0008, n)))
    a = np.concatenate([[100.0], f[:-1]])
    folga = np.abs(g.normal(0, 0.05, n))
    volume = g.lognormal(3, 1, n)
    return pd.DataFrame({"abertura": a, "maxima": np.maximum(a, f) + folga, "minima": np.minimum(a, f) - folga, "fechamento": f, "volume": volume, "negocios": 10, "volume_comprador": volume / 2},
                        index=pd.date_range(INICIO, periods=n, freq="1min", tz="UTC", name="abertura_em"))


def test_ultima_vela_fechada():
    assert ultima_vela_fechada(datetime(2026, 1, 1, 10, 14, tzinfo=timezone.utc), 15) == pd.Timestamp("2026-01-01 10:14", tz="UTC")
    assert ultima_vela_fechada(datetime(2026, 1, 1, 10, 20, tzinfo=timezone.utc), 15) == pd.Timestamp("2026-01-01 10:14", tz="UTC")
    assert ultima_vela_fechada(datetime(2026, 1, 1, 10, 4, tzinfo=timezone.utc), 5) == pd.Timestamp("2026-01-01 10:04", tz="UTC")


class _Velas:
    def __init__(self, v):
        self.v = v

    def ultima_abertura(self, par):
        return self.v.index[-1].to_pydatetime()

    def ler(self, par, inicio=None, fim=None, como_de=None):
        return self.v


def _carteira(tmp_path, v, agora):
    c = Carteira(tmp_path, ["ETHUSDT"], relogio=lambda: agora)
    c.velas = _Velas(v)
    return c


def test_nao_repete_a_mesma_vela_nem_depois_de_reiniciar(tmp_path):
    v = _velas().iloc[:7200]  # a última vela fecha em 15 e em 5 minutos
    agora = v.index[-1].to_pydatetime() + timedelta(minutes=1)
    c = _carteira(tmp_path, v, agora)
    c.ciclo()
    gravados = ArmazemEventos(tmp_path).ler("carteira", "ETHUSDT")
    assert not gravados.empty and (gravados["recebido_em"] == pd.Timestamp(agora)).all()
    assert c.ciclo() == 0
    novo = _carteira(tmp_path, v, agora + timedelta(minutes=1))
    assert novo.ciclo() == 0
    assert len(ArmazemEventos(tmp_path).ler("carteira", "ETHUSDT")) == len(gravados)


def test_dado_velho_nao_gera_sinal(tmp_path):
    v = _velas().iloc[:7200]
    c = _carteira(tmp_path, v, v.index[-1].to_pydatetime() + timedelta(minutes=30))
    assert c.ciclo() == 0
    assert ArmazemEventos(tmp_path).ler("carteira", "ETHUSDT").empty


def test_sinal_nao_usa_vela_depois_da_decisao(tmp_path):
    v = _velas()
    vela = v.index[7199]
    a = _carteira(tmp_path / "a", v.iloc[:7200], vela.to_pydatetime() + timedelta(minutes=1))
    a.ciclo()
    # Mais 7 minutos dentro da próxima vela: a decisão da vela 7199 tem de ser a mesma.
    b = _carteira(tmp_path / "b", v.iloc[:7207], vela.to_pydatetime() + timedelta(minutes=2))
    b.velas.ultima_abertura = lambda par: vela.to_pydatetime()
    b.ciclo()
    x = ArmazemEventos(tmp_path / "a").ler("carteira", "ETHUSDT").sort_values(["tempo", "estrategia"]).reset_index(drop=True)
    y = ArmazemEventos(tmp_path / "b").ler("carteira", "ETHUSDT").sort_values(["tempo", "estrategia"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(x.drop(columns="recebido_em"), y.drop(columns="recebido_em"))


def test_saldo_em_unidades_e_uma_operacao_de_cada_vez(tmp_path, monkeypatch):
    n = 120
    t = pd.date_range(INICIO, periods=n, freq="1min", tz="UTC", name="abertura_em")
    f = 100 + 0.1 * np.arange(n)  # só sobe
    a = np.concatenate([[100.0], f[:-1]])
    v = pd.DataFrame({"abertura": a, "maxima": f, "minima": a, "fechamento": f, "volume": 1.0}, index=t)
    ArmazemEventos(tmp_path).gravar("carteira", "ETHUSDT", [
        {"estrategia": "A", "tempo": "5min", "expiracao": 5, "direcao": 1, "ocorrido_em": t[9], "recebido_em": t[10]},
        {"estrategia": "A", "tempo": "5min", "expiracao": 5, "direcao": 1, "ocorrido_em": t[11], "recebido_em": t[12]},  # operação aberta: ignorado
        {"estrategia": "A", "tempo": "5min", "expiracao": 5, "direcao": -1, "ocorrido_em": t[29], "recebido_em": t[30]},
        {"estrategia": "sem sinal", "tempo": "5min", "expiracao": 5, "direcao": 0, "ocorrido_em": t[34], "recebido_em": t[35]}])
    monkeypatch.setattr(ArmazemVelas, "ler", lambda self, par, inicio=None, fim=None, como_de=None: v)
    r = placar(tmp_path, ["ETHUSDT"], 0.85)
    assert len(r) == 1 and r[0]["estrategia"] == "A"
    assert (r[0]["operacoes"], r[0]["ganhos"], r[0]["perdas"]) == (2, 1, 1)
    assert r[0]["saldo_unidades"] == pytest.approx(-0.15)


def test_operacao_ainda_aberta_nao_conta_no_saldo(tmp_path, monkeypatch):
    t = pd.date_range(INICIO, periods=40, freq="1min", tz="UTC", name="abertura_em")
    f = 100 + 0.1 * np.arange(40)
    v = pd.DataFrame({"abertura": f, "maxima": f, "minima": f, "fechamento": f + 0.05, "volume": 1.0}, index=t)
    ArmazemEventos(tmp_path).gravar("carteira", "ETHUSDT", [{"estrategia": "A", "tempo": "15min", "expiracao": 15, "direcao": 1, "ocorrido_em": t[35], "recebido_em": t[36]}])
    monkeypatch.setattr(ArmazemVelas, "ler", lambda self, par, inicio=None, fim=None, como_de=None: v)
    r = placar(tmp_path, ["ETHUSDT"], 0.85)
    assert r[0]["operacoes"] == 0 and r[0]["abertas"] == 1 and r[0]["saldo_unidades"] == 0


def test_modelo_so_opera_com_corte_do_passado():
    g = np.random.default_rng(0)
    n = 400
    p = pd.DataFrame({"modelo": "M", "horizonte": 15, "ocorrido_em": pd.date_range(INICIO, periods=n, freq="15min", tz="UTC"), "prob_sobe": 0.5 + g.uniform(-0.1, 0.1, n), "direcao": 1})
    s = sinais_do_modelo(p)
    assert s["ocorrido_em"].min() >= p["ocorrido_em"].iloc[100]  # antes disso não existe passado
    assert 0.1 < len(s) / 300 < 0.35 and (s["estrategia"] == ESTRATEGIA_MODELO).all()
    # Previsões futuras não alteram a escolha do passado.
    parcial = sinais_do_modelo(p.iloc[:300])
    assert set(parcial["ocorrido_em"]) == set(s[s["ocorrido_em"] <= p["ocorrido_em"].iloc[299]]["ocorrido_em"])

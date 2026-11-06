"""Histórico de moedas e ouro: datas, escala e pausas conferidas sem rede."""

from __future__ import annotations

import lzma
import struct
from datetime import date

import httpx
import pandas as pd
import pytest

from mneme.dados.armazem import ArmazemVelas
from mneme.dados.dukascopy import baixar_dia, importar, ler_dia, url_do_dia

REGISTRO = struct.Struct(">5if")


def _dia(*linhas):
    return lzma.compress(b"".join(REGISTRO.pack(*l) for l in linhas))


def test_mes_da_url_comeca_em_zero():
    assert "/EURUSD/2026/00/05/" in url_do_dia("EURUSD", date(2026, 1, 5))
    assert "/XAUUSD/2026/11/31/" in url_do_dia("XAUUSD", date(2026, 12, 31))


@pytest.mark.parametrize("par,bruto,preco", [("EURUSD", 111944, 1.11944), ("USDJPY", 157979, 157.979), ("XAUUSD", 4111725, 4111.725)])
def test_escala_por_ativo(par, bruto, preco):
    l = ler_dia(_dia((0, bruto, bruto, bruto, bruto, 10.0)), par, date(2026, 10, 15))
    assert l[0]["abertura"] == pytest.approx(preco)


def test_ordem_dos_campos_e_horario():
    l = ler_dia(_dia((60, 100000, 100500, 99500, 101000, 8.0)), "EURUSD", date(2026, 10, 15))[0]
    assert l["abertura_em"] == pd.Timestamp("2026-10-15 00:01", tz="UTC")
    assert (l["abertura"], l["fechamento"], l["minima"], l["maxima"]) == (1.0, 1.005, 0.995, 1.01)
    assert l["volume_comprador"] == 4.0 and l["recebido_em"] is None  # histórico, sem hora de chegada


def test_minuto_sem_volume_e_mercado_fechado():
    l = ler_dia(_dia((0, 100000, 100000, 100000, 100000, 0.0), (60, 100000, 100000, 100000, 100000, 3.0)), "EURUSD", date(2026, 10, 15))
    assert len(l) == 1 and l[0]["abertura_em"].minute == 1


def test_arquivo_vazio_nao_quebra():
    assert ler_dia(b"", "EURUSD", date(2026, 10, 15)) == []


def _cliente(respostas):
    fila = list(respostas)
    return httpx.Client(transport=httpx.MockTransport(lambda pedido: fila.pop(0)))


def test_espera_e_tenta_de_novo_quando_a_fonte_limita():
    c = _cliente([httpx.Response(503), httpx.Response(200, content=_dia((0, 100000, 100000, 100000, 100000, 1.0)))])
    assert len(baixar_dia(c, "EURUSD", date(2026, 10, 15), espera=0)) == 1


def test_dia_que_nao_veio_fica_marcado_e_404_e_dia_vazio():
    assert baixar_dia(_cliente([httpx.Response(503)] * 2), "EURUSD", date(2026, 10, 15), tentativas=2, espera=0) is None
    assert baixar_dia(_cliente([httpx.Response(404)]), "EURUSD", date(2026, 10, 15), espera=0) == []


def test_importa_grava_e_pula_sabado(tmp_path):
    pedidos = []

    def responder(pedido):
        pedidos.append(str(pedido.url))
        return httpx.Response(200, content=_dia((0, 100000, 100100, 99900, 100200, 5.0), (60, 100100, 100000, 99800, 100300, 2.0)))

    a = ArmazemVelas(tmp_path)
    r = importar(a, "EURUSD", date(2026, 10, 16), date(2026, 10, 18), httpx.Client(transport=httpx.MockTransport(responder)), pausa=0)  # sexta, sábado e domingo
    assert len(pedidos) == 2 and not any("/2026/09/17/" in p for p in pedidos)
    assert r["velas_novas"] == 4 and r["dias_com_falha"] == []
    assert a.ler("EURUSD")["origem"].iloc[0] == "dukascopy"

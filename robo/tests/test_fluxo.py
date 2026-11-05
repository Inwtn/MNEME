"""Entrega 2: trades, livro, derivativos e liquidações."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd
import pytest

from mneme.dados.binance_fluxo import FonteFluxo, liquidacao_do_stream, livro_do_stream, trade_do_stream
from mneme.dados.coleta_fluxo import ColetorFluxo, importar_derivativos
from mneme.dados.eventos import ArmazemEventos
from mneme.fluxo import lacunas_livro, livro_por_minuto, trades_faltando, trades_por_minuto

INICIO = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
FUTURO = INICIO + timedelta(days=3)


def _ms(segundos: float = 0) -> int:
    return int((INICIO + timedelta(seconds=segundos)).timestamp() * 1000)


def _trade(id_, segundos=0.0, preco=100.0, qtd=1.0, comprador_agressor=True, recebido=None):
    return {"agg_id": id_, "preco": preco, "quantidade": qtd, "comprador_agressor": comprador_agressor,
            "ocorrido_em": INICIO + timedelta(seconds=segundos), "recebido_em": recebido or INICIO + timedelta(seconds=segundos), "origem": "ws"}


def _msg_trade(id_, segundos=0.0, par="BTCUSDT", m=False):
    return json.dumps({"stream": f"{par.lower()}@aggTrade", "data": {"s": par, "a": id_, "p": "100", "q": "2", "T": _ms(segundos), "m": m}})


LIVRO = {"lastUpdateId": 9, "bids": [["100", "3"], ["99", "1"]], "asks": [["101", "1"], ["102", "1"]]}


def _msg_livro(par="BTCUSDT"):
    return json.dumps({"stream": f"{par.lower()}@depth20@1000ms", "data": LIVRO})


# ---------- leitura das mensagens ----------

def test_trade_marca_o_agressor_certo():
    _, comprador = trade_do_stream({"s": "BTCUSDT", "a": 1, "p": "1", "q": "1", "T": _ms(), "m": False}, INICIO)
    _, vendedor = trade_do_stream({"s": "BTCUSDT", "a": 2, "p": "1", "q": "1", "T": _ms(), "m": True}, INICIO)
    assert comprador["comprador_agressor"] is True
    assert vendedor["comprador_agressor"] is False


def test_livro_calcula_spread_desequilibrio_e_profundidade():
    _, l = livro_do_stream("BTCUSDT", LIVRO, INICIO)
    assert l["spread_bps"] == pytest.approx(1 / 100.5 * 10_000)
    assert l["desequilibrio_5"] == pytest.approx((4 - 2) / 6)
    assert l["profundidade_compra"] == pytest.approx(399)
    assert l["profundidade_venda"] == pytest.approx(203)


def test_livro_vazio_e_recusado():
    with pytest.raises(ValueError):
        livro_do_stream("BTCUSDT", {"lastUpdateId": 1, "bids": [], "asks": []}, INICIO)


def test_liquidacao_usa_o_preco_medio_e_a_quantidade_executada():
    _, l = liquidacao_do_stream({"o": {"s": "BTCUSDT", "S": "SELL", "p": "90", "ap": "91", "q": "5", "z": "4", "T": _ms()}}, INICIO)
    assert (l["lado"], l["preco"], l["quantidade"]) == ("SELL", 91.0, 4.0)


# ---------- armazém ----------

def test_grava_em_partes_e_nao_duplica_ao_ler(tmp_path):
    a = ArmazemEventos(tmp_path)
    a.gravar("trades", "BTCUSDT", [_trade(1), _trade(2)])
    a.gravar("trades", "BTCUSDT", [_trade(2), _trade(3)])
    assert a.ler("trades", "BTCUSDT")["agg_id"].tolist() == [1, 2, 3]
    assert a.ultimo("trades", "BTCUSDT", "agg_id") == 3


def test_compactacao_junta_o_dia_fechado_e_preserva_tudo(tmp_path):
    a = ArmazemEventos(tmp_path)
    a.gravar("trades", "BTCUSDT", [_trade(1)])
    a.gravar("trades", "BTCUSDT", [_trade(2)])
    a.gravar("trades", "BTCUSDT", [_trade(3, segundos=86_400)])  # dia seguinte, ainda aberto
    assert a.compactar(INICIO + timedelta(days=1, seconds=10)) == 1
    pasta = tmp_path / "fluxo" / "trades" / "BTCUSDT"
    assert (pasta / "2026-01-01.parquet").is_file() and not (pasta / "2026-01-01").exists()
    assert (pasta / "2026-01-02").is_dir()
    assert a.ler("trades", "BTCUSDT")["agg_id"].tolist() == [1, 2, 3]


def test_compactar_de_novo_junta_com_o_que_ja_estava(tmp_path):
    a = ArmazemEventos(tmp_path)
    a.gravar("trades", "BTCUSDT", [_trade(1)])
    depois = INICIO + timedelta(days=1)
    a.compactar(depois)
    a.gravar("trades", "BTCUSDT", [_trade(2)])  # chegou atrasado, por recuperação
    a.compactar(depois)
    assert a.ler("trades", "BTCUSDT")["agg_id"].tolist() == [1, 2]


def test_religar_com_batimento_na_pasta_nao_quebra_a_manutencao(tmp_path):
    """O serviço entrou em ciclo de reinício: a compactação tratava o arquivo de batimento como pasta."""
    c = _coletor(tmp_path)
    c.receber_spot(_msg_trade(1))
    c.descarregar()
    assert c.batimento.is_file()
    assert c.armazem.compactar(INICIO + timedelta(days=1)) == 1
    novo = ColetorFluxo(["BTCUSDT"], c.armazem, FonteFalsa(), lambda: INICIO + timedelta(days=2), uso_disco=lambda: 10.0)
    novo.manutencao()
    assert novo.ultimo_trade["BTCUSDT"] == 1


def test_compactar_tolera_outro_processo_compactando_junto(tmp_path, monkeypatch):
    a = ArmazemEventos(tmp_path)
    a.gravar("trades", "BTCUSDT", [_trade(1)])
    original = a._unir

    def outro_processo_chegou_antes(tipo, arquivos):
        raise FileNotFoundError("já compactado")

    monkeypatch.setattr(a, "_unir", outro_processo_chegou_antes)
    assert a.compactar(INICIO + timedelta(days=1)) == 0
    monkeypatch.setattr(a, "_unir", original)
    assert a.compactar(INICIO + timedelta(days=1)) == 1


def test_limpar_respeita_a_retencao(tmp_path):
    a = ArmazemEventos(tmp_path)
    a.gravar("livro", "BTCUSDT", [{"ocorrido_em": INICIO, "recebido_em": INICIO, "x": 1}])
    a.gravar("livro", "BTCUSDT", [{"ocorrido_em": INICIO + timedelta(days=40), "recebido_em": INICIO, "x": 2}])
    assert a.limpar("livro", 30, INICIO + timedelta(days=41)) == 1
    assert a.ler("livro", "BTCUSDT")["x"].tolist() == [2]


def test_ve_so_o_que_ja_tinha_chegado(tmp_path):
    a = ArmazemEventos(tmp_path)
    a.gravar("trades", "BTCUSDT", [_trade(1), _trade(2, segundos=1, recebido=INICIO + timedelta(seconds=60))])
    assert a.ler("trades", "BTCUSDT", como_de=INICIO + timedelta(seconds=30))["agg_id"].tolist() == [1]
    assert len(a.ler("trades", "BTCUSDT", como_de=INICIO + timedelta(seconds=60))) == 2


# ---------- atributos ----------

def test_trades_por_minuto_soma_e_mede_a_agressao():
    t = pd.DataFrame([_trade(1, 0, 100, 3, True), _trade(2, 10, 110, 1, False), _trade(3, 65, 100, 2, True)])
    t["ocorrido_em"] = pd.to_datetime(t["ocorrido_em"], utc=True)
    x = trades_por_minuto(t)
    primeiro = x.iloc[0]
    assert primeiro["volume"] == 4 and primeiro["volume_comprador"] == 3 and primeiro["negocios"] == 2
    assert primeiro["delta"] == 2 and primeiro["delta_fracao"] == 0.5
    assert primeiro["vwap"] == pytest.approx(102.5)
    assert primeiro["concentracao"] == 0.75
    assert len(x) == 2


def test_minuto_aberto_fica_de_fora():
    t = pd.DataFrame([_trade(1, 0), _trade(2, 65)])
    t["ocorrido_em"] = pd.to_datetime(t["ocorrido_em"], utc=True)
    assert len(trades_por_minuto(t, ate=INICIO + timedelta(seconds=70))) == 1


def test_minuto_nao_muda_com_trades_futuros():
    t = pd.DataFrame([_trade(i, i * 10, 100 + i) for i in range(30)])
    t["ocorrido_em"] = pd.to_datetime(t["ocorrido_em"], utc=True)
    completo = trades_por_minuto(t).iloc[0]
    so_passado = trades_por_minuto(t[t["ocorrido_em"] < pd.Timestamp(INICIO + timedelta(seconds=60))]).iloc[0]
    pd.testing.assert_series_equal(completo, so_passado)


def test_livro_por_minuto_e_lacunas():
    _, base = livro_do_stream("BTCUSDT", LIVRO, INICIO)
    fotos = [{**base, "ocorrido_em": INICIO + timedelta(seconds=s)} for s in (0, 1, 2, 30)]
    l = pd.DataFrame(fotos)
    l["ocorrido_em"] = pd.to_datetime(l["ocorrido_em"], utc=True)
    assert livro_por_minuto(l)["amostras"].iloc[0] == 4
    assert [segundos for _, segundos in lacunas_livro(l)] == [28.0]


def test_trades_faltando_conta_ids_ausentes():
    assert trades_faltando(pd.DataFrame({"agg_id": [1, 2, 5, 6, 6]})) == 2


# ---------- coletor ----------

class FonteFalsa(FonteFluxo):
    def __init__(self, paginas=None, erro=False):
        self.paginas, self.erro, self.pedidos = paginas or {}, erro, []

    def trades_desde(self, par, de_id, agora):
        self.pedidos.append((par, de_id))
        if self.erro:
            raise httpx.ConnectError("fora")
        return self.paginas.get(de_id, [])

    def derivativos(self, par, agora):
        if par == "ETHUSDT":
            raise httpx.ConnectError("fora")
        return {"ocorrido_em": agora, "recebido_em": agora, "preco_marca": 1.0, "preco_indice": 1.0, "funding": 0.0001,
                "proximo_funding_em": agora, "open_interest": 5.0}


def _coletor(tmp_path, **kw):
    kw.setdefault("uso_disco", lambda: 10.0)
    return ColetorFluxo(["BTCUSDT"], ArmazemEventos(tmp_path), kw.pop("fonte", FonteFalsa()), lambda: INICIO, **kw)


def test_coletor_guarda_e_descarrega(tmp_path):
    c = _coletor(tmp_path)
    c.receber_spot(_msg_trade(1))
    c.receber_spot(_msg_livro())
    assert c.descarregar() == 2
    assert not c.buffers[("trades", "BTCUSDT")]
    assert c.armazem.ler("trades", "BTCUSDT")["agg_id"].tolist() == [1]
    assert len(c.armazem.ler("livro", "BTCUSDT")) == 1
    assert c.batimento.exists()


def test_mensagem_estranha_nao_derruba(tmp_path):
    c = _coletor(tmp_path)
    for ruim in ("não é json {", json.dumps({"oi": 1}), json.dumps({"stream": "btcusdt@aggTrade", "data": {"a": 1}}),
                 json.dumps({"stream": "btcusdt@depth20@1000ms", "data": {"bids": []}})):
        c.receber_spot(ruim)
        c.receber_futuros(ruim)
    assert c.descarregar() == 0


def test_recupera_trades_perdidos_e_continua_do_ponto_certo(tmp_path):
    a = ArmazemEventos(tmp_path)
    a.gravar("trades", "BTCUSDT", [_trade(10)])
    fonte = FonteFalsa({11: [_trade(11), _trade(12)]})
    c = ColetorFluxo(["BTCUSDT"], a, fonte, lambda: INICIO, uso_disco=lambda: 10.0)
    assert c.ultimo_trade["BTCUSDT"] == 10  # veio do disco, depois de reiniciar
    assert c.recuperar_trades() == 2
    c.descarregar()
    assert a.ler("trades", "BTCUSDT")["agg_id"].tolist() == [10, 11, 12]
    assert c.ultimo_trade["BTCUSDT"] == 12


def test_recuperacao_cobre_o_que_passou_antes_do_primeiro_trade_novo(tmp_path):
    """O stream volta com o trade 15: a recuperação tem de partir do 10, e não do 15, para não abrir buraco."""
    fonte = FonteFalsa({11: [_trade(i) for i in range(11, 15)]})
    c = _coletor(tmp_path, fonte=fonte)
    c.ultimo_trade["BTCUSDT"] = 10
    recuperar = c._preparar_recuperacao()
    c.receber_spot(_msg_trade(15))
    assert recuperar() == 4
    assert fonte.pedidos[0] == ("BTCUSDT", 11)
    assert c.ultimo_trade["BTCUSDT"] == 15
    c.descarregar()
    assert trades_faltando(c.armazem.ler("trades", "BTCUSDT")) == 0


def test_recuperacao_aguenta_rest_fora_do_ar(tmp_path):
    c = _coletor(tmp_path, fonte=FonteFalsa(erro=True))
    c.ultimo_trade["BTCUSDT"] = 5
    assert c.recuperar_trades() == 0
    assert c.ultimo_trade["BTCUSDT"] == 5


def test_falha_de_derivativos_em_um_par_nao_para_os_outros(tmp_path):
    c = ColetorFluxo(["ETHUSDT", "BTCUSDT"], ArmazemEventos(tmp_path), FonteFalsa(), lambda: INICIO, uso_disco=lambda: 10.0)
    assert c.consultar_derivativos() == 1


@pytest.mark.parametrize("uso,livro_gravado,trade_gravado", [(10, 1, 1), (85, 0, 1), (92, 0, 0)])
def test_limites_de_disco(tmp_path, uso, livro_gravado, trade_gravado):
    c = _coletor(tmp_path, uso_disco=lambda: uso)
    c.receber_spot(_msg_trade(1))
    c.receber_spot(_msg_livro())
    c.descarregar()
    assert len(c.armazem.ler("livro", "BTCUSDT")) == livro_gravado
    assert len(c.armazem.ler("trades", "BTCUSDT")) == trade_gravado
    assert c.descartados["livro"] == 1 - livro_gravado


def test_falha_de_gravacao_mantem_os_eventos_em_memoria(tmp_path, monkeypatch):
    c = _coletor(tmp_path)
    c.receber_spot(_msg_trade(1))

    def falha(*_):
        raise PermissionError("sem permissão")

    monkeypatch.setattr(c.armazem, "gravar", falha)
    assert c.descarregar() == 0
    assert len(c.buffers[("trades", "BTCUSDT")]) == 1
    monkeypatch.undo()
    assert c.descarregar() == 1


class ConexaoFalsa:
    def __init__(self, mensagens, ao_acabar=None):
        self.mensagens, self.ao_acabar = list(mensagens), ao_acabar

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.mensagens:
            return self.mensagens.pop(0)
        if self.ao_acabar:
            self.ao_acabar()
        raise OSError("caiu")


def test_reconecta_recupera_e_grava_tudo_ao_desligar(tmp_path):
    fonte = FonteFalsa({2: [_trade(2), _trade(3)]})
    c = _coletor(tmp_path, fonte=fonte)
    parar_evento = asyncio.Event()
    conexoes = []

    def spot():
        conexoes.append(1)
        if len(conexoes) == 1:
            return ConexaoFalsa([_msg_trade(1)])
        return ConexaoFalsa([_msg_trade(4)], parar_evento.set)

    def futuros():
        msg = json.dumps({"stream": "btcusdt@forceOrder", "data": {"o": {"s": "BTCUSDT", "S": "BUY", "p": "1", "ap": "1", "q": "1", "z": "1", "T": _ms()}}})
        return ConexaoFalsa([msg])

    asyncio.run(c.rodar(parar_evento, spot, futuros, espera_inicial=0))
    assert len(conexoes) >= 2
    assert c.armazem.ler("trades", "BTCUSDT")["agg_id"].tolist() == [1, 2, 3, 4]
    assert trades_faltando(c.armazem.ler("trades", "BTCUSDT")) == 0
    assert len(c.armazem.ler("liquidacoes", "BTCUSDT")) == 1


def test_fonte_rest_le_derivativos_e_historicos():
    def responder(pedido):
        rota = pedido.url.path
        if rota.endswith("premiumIndex"):
            return httpx.Response(200, json={"markPrice": "10", "indexPrice": "11", "lastFundingRate": "0.0001", "nextFundingTime": _ms(), "time": _ms()})
        if rota.endswith("openInterest"):
            return httpx.Response(200, json={"openInterest": "7"})
        if rota.endswith("fundingRate"):
            return httpx.Response(200, json=[{"fundingTime": _ms(), "fundingRate": "0.0002"}])
        if rota.endswith("openInterestHist"):
            return httpx.Response(200, json=[{"timestamp": _ms(), "sumOpenInterest": "8", "sumOpenInterestValue": "80"}])
        return httpx.Response(404)

    fonte = FonteFluxo(httpx.Client(transport=httpx.MockTransport(responder)))
    d = fonte.derivativos("BTCUSDT", INICIO)
    assert (d["preco_marca"], d["funding"], d["open_interest"]) == (10.0, 0.0001, 7.0)
    assert fonte.funding_historico("BTCUSDT", INICIO, FUTURO)[0]["funding"] == 0.0002
    assert fonte.open_interest_historico("BTCUSDT", INICIO, FUTURO)[0]["open_interest_usd"] == 80.0


def test_open_interest_pagina_do_fim_para_o_comeco():
    """Como a Binance: de cada intervalo, devolve os 500 pontos mais recentes, em ordem crescente."""
    passo = 300_000
    todos = [_ms() + i * passo for i in range(1200)]

    def responder(pedido):
        de, ate = int(pedido.url.params["startTime"]), int(pedido.url.params["endTime"])
        dentro = [t for t in todos if de <= t <= ate][-500:]
        return httpx.Response(200, json=[{"timestamp": t, "sumOpenInterest": "1", "sumOpenInterestValue": "2"} for t in dentro])

    fonte = FonteFluxo(httpx.Client(transport=httpx.MockTransport(responder)))
    linhas = fonte.open_interest_historico("BTCUSDT", INICIO, FUTURO + timedelta(days=30))
    assert len(linhas) == 1200
    assert len({l["ocorrido_em"] for l in linhas}) == 1200


def test_importar_derivativos_grava_sem_hora_de_chegada(tmp_path):
    class F(FonteFluxo):
        def __init__(self):
            pass

        def funding_historico(self, par, inicio, fim):
            return [{"ocorrido_em": INICIO, "recebido_em": None, "funding": 0.0002}]

        def open_interest_historico(self, par, inicio, fim):
            return [{"ocorrido_em": INICIO, "recebido_em": None, "open_interest": 8.0, "open_interest_usd": 80.0}]

    a = ArmazemEventos(tmp_path)
    assert importar_derivativos(a, ["BTCUSDT"], 1, F(), FUTURO) == {"funding": 1, "open_interest": 1}
    lido = a.ler("funding", "BTCUSDT", como_de=INICIO + timedelta(hours=1))
    assert len(lido) == 1 and pd.isna(lido["recebido_em"].iloc[0])

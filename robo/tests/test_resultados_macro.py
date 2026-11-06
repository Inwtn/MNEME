"""Calendário com resultado e surpresa, e o estudo de reação dos ativos, sem usar nada antes de ser público."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import httpx
import numpy as np
import pandas as pd
import pytest

from mneme.dados.eventos import ArmazemEventos
from mneme.dados.resultados_macro import FonteResultados, ResultadosAoVivo, classe_do_evento, divulgados_ate, divulgados_e_agenda, ler_dia, numero, surpresas
from mneme.laboratorio.estudo_eventos import atributos_macro, com_macro, ganho_da_agenda, reacoes, resumir, volatilidade_em_torno

AGORA = datetime(2026, 11, 5, 15, tzinfo=timezone.utc)
INICIO = pd.Timestamp("2026-01-01", tz="UTC")


@pytest.mark.parametrize("texto,esperado", [("3.1%", 3.1), ("65K", 65_000), ("-1.2B", -1.2e9), ("$2.5", 2.5), ("&nbsp;", None), ("", None), (None, None), ("0.3%&nbsp;", 0.3), ("1,200", 1200.0), ("sem dado", None)])
def test_numero(texto, esperado):
    assert numero(texto) == esperado


@pytest.mark.parametrize("nome,classe", [("CPI", "inflacao_cpi"), ("Core CPI MoM", "inflacao_cpi"), ("Nonfarm Payrolls", "emprego_payroll"), ("Initial Jobless Claims", "pedidos_desemprego"), ("GDP Annualized", "pib"), ("Fed Interest Rate Decision", "juros_fed"), ("Baker Hughes Rig Count", None)])
def test_classe(nome, classe):
    assert classe_do_evento(nome) == classe


RESPOSTA = {"data": {"rows": [
    {"gmt": "08:30", "country": "United States", "eventName": "CPI", "actual": "2.8%", "consensus": "3.0%", "previous": "3.1%"},
    {"gmt": "24H", "country": "Japan", "eventName": "Sem hora", "actual": "1", "consensus": "1", "previous": "1"},
    {"gmt": "09:00", "country": "Germany", "eventName": "German CPI", "actual": "", "consensus": "2%", "previous": "&nbsp;"}]}}


def test_le_o_dia_com_consenso_e_resultado():
    linhas = ler_dia(RESPOSTA, date(2026, 11, 5), AGORA)
    assert len(linhas) == 2
    us = next(l for l in linhas if l["pais"] == "United States")
    assert (us["resultado"], us["consenso"], us["anterior"], us["classe"]) == (2.8, 3.0, 3.1, "inflacao_cpi")
    assert us["ocorrido_em"] == pd.Timestamp("2026-11-05 13:30", tz="UTC")
    de = next(l for l in linhas if l["pais"] == "Germany")
    assert de["resultado"] is None and de["classe"] is None  # só eventos americanos entram no recorte


@pytest.mark.parametrize("dia,hora,utc", [
    (date(2026, 7, 14), "07:30", "2026-07-14 12:30"),  # CPI no horário de verão de Nova York
    (date(2026, 11, 11), "08:30", "2026-11-11 13:30"),  # CPI no horário de inverno
    (date(2026, 7, 29), "13:00", "2026-07-29 18:00"),  # FOMC no verão
    (date(2026, 12, 9), "14:00", "2026-12-09 19:00"),  # FOMC no inverno
    (date(2026, 11, 5), "21:00", "2026-11-06 02:00"),  # à noite, já é o dia seguinte em UTC
])
def test_horario_da_fonte_vira_utc(dia, hora, utc):
    corpo = {"data": {"rows": [{"gmt": hora, "country": "United States", "eventName": "CPI", "actual": "", "consensus": "", "previous": ""}]}}
    assert ler_dia(corpo, dia, None)[0]["ocorrido_em"] == pd.Timestamp(utc, tz="UTC")


def test_fonte_chama_a_data_certa_e_periodo_sobrevive_a_falha():
    datas = []

    def responder(pedido):
        datas.append(pedido.url.params["date"])
        return httpx.Response(500) if pedido.url.params["date"] == "2026-11-02" else httpx.Response(200, json=RESPOSTA)

    fonte = FonteResultados(httpx.Client(transport=httpx.MockTransport(responder)), pausa=0)
    linhas = fonte.periodo(date(2026, 11, 1), date(2026, 11, 3))
    assert datas == ["2026-11-01", "2026-11-02", "2026-11-03"] and len(linhas) == 4


def _eventos(valores, nome="CPI", classe="inflacao_cpi", recebido=None):
    tempos = pd.date_range("2025-01-10 13:30", periods=len(valores), freq="30D", tz="UTC")
    return pd.DataFrame({"id": [f"{nome}{i}" for i in range(len(valores))], "ocorrido_em": tempos, "recebido_em": pd.NaT if recebido is None else recebido, "pais": "United States", "nome": nome, "classe": classe,
                         "resultado": [3.0 + s for s in valores], "consenso": 3.0, "anterior": 3.0})


def test_surpresa_exemplo_do_pedido():
    s = surpresas(_eventos([0.1, -0.1, 0.2, -0.2, 0.1, -0.1, -0.2]))
    assert s["surpresa"].iloc[-1] == pytest.approx(-0.2)
    assert s["surpresa_z"].iloc[-1] < 0


def test_surpresa_padronizada_so_usa_o_passado():
    valores = [0.1, -0.1, 0.2, -0.2, 0.1, -0.1, 0.3, 0.2, -0.3]
    completo = surpresas(_eventos(valores))
    parcial = surpresas(_eventos(valores[:7]))
    assert completo["surpresa_z"].iloc[6] == pytest.approx(parcial["surpresa_z"].iloc[6])
    assert completo["surpresa_z"].iloc[:6].isna().all()  # sem histórico, não há escala


def test_sem_consenso_ou_resultado_nao_vira_surpresa_zero():
    e = _eventos([0.1, 0.2])
    e.loc[0, "resultado"] = None
    e.loc[1, "consenso"] = None
    assert surpresas(e).empty


def test_resultado_so_e_publico_depois_do_horario_e_da_chegada():
    e = _eventos([0.1, 0.2])
    e["recebido_em"] = pd.to_datetime([pd.NaT, e["ocorrido_em"].iloc[1] + timedelta(minutes=5)], utc=True)
    assert len(divulgados_ate(e, e["ocorrido_em"].iloc[0] - timedelta(minutes=1))) == 0
    assert len(divulgados_ate(e, e["ocorrido_em"].iloc[0])) == 1
    assert len(divulgados_ate(e, e["ocorrido_em"].iloc[1] + timedelta(minutes=1))) == 1  # ainda não tinha chegado
    assert len(divulgados_ate(e, e["ocorrido_em"].iloc[1] + timedelta(minutes=6))) == 2


def test_ao_vivo_guarda_a_chegada_do_resultado_e_as_revisoes(tmp_path):
    respostas = {"valor": "", "anterior": "3.1%"}

    def responder(pedido):
        return httpx.Response(200, json={"data": {"rows": [{"gmt": "13:30", "country": "United States", "eventName": "CPI", "actual": respostas["valor"], "consensus": "3.0%", "previous": respostas["anterior"]}]}})

    ao_vivo = ResultadosAoVivo(FonteResultados(httpx.Client(transport=httpx.MockTransport(responder)), pausa=0))
    armazem = ArmazemEventos(tmp_path)
    armazem.gravar("resultados_macro", "GLOBAL", ao_vivo.coletar(AGORA))  # dois dias lidos, mesma resposta simulada
    assert ao_vivo.coletar(AGORA + timedelta(minutes=5)) == []  # sem mudança, nada novo
    respostas["valor"] = "2.8%"
    armazem.gravar("resultados_macro", "GLOBAL", ao_vivo.coletar(AGORA + timedelta(minutes=10)))
    respostas["anterior"] = "3.2%"
    armazem.gravar("resultados_macro", "GLOBAL", ao_vivo.coletar(AGORA + timedelta(minutes=15)))
    hoje = armazem.ler("resultados_macro", "GLOBAL")
    hoje = hoje[hoje["ocorrido_em"].dt.date == AGORA.date()].sort_values("recebido_em")
    assert hoje["resultado"].isna().tolist() == [True, False, False]
    assert hoje["anterior"].tolist() == [3.1, 3.1, 3.2]
    assert hoje["recebido_em"].iloc[1] == pd.Timestamp(AGORA + timedelta(minutes=10))


def test_agenda_futura_fica_e_resultado_nao_chegado_some():
    e = _eventos([0.1, 0.2])
    corte = e["ocorrido_em"].iloc[0] + timedelta(minutes=1)
    x = divulgados_e_agenda(e, corte)
    assert len(x) == 2 and pd.notna(x["resultado"].iloc[0]) and pd.isna(x["resultado"].iloc[1])
    assert x["consenso"].iloc[1] == 3.0  # o consenso existe antes do evento


def test_com_macro_vazio_nao_inventa_zero():
    x = pd.DataFrame({"a": [1.0, 2.0]}, index=pd.date_range(INICIO, periods=2, freq="1min", tz="UTC"))
    saida = com_macro(x, pd.DataFrame())
    assert saida["e_ultima_surpresa_z"].isna().all() and saida["e_min_ate_macro"].isna().all()


def test_agenda_futura_chega_aos_atributos_mesmo_sem_resultado():
    e = _eventos([0.1, 0.2, 0.3])
    corte = e["ocorrido_em"].iloc[0] + timedelta(days=1)
    x = pd.DataFrame({"a": [1.0]}, index=pd.DatetimeIndex([corte]))
    saida = com_macro(x, divulgados_e_agenda(e, corte + timedelta(minutes=1)))
    assert saida["e_min_ate_macro"].iloc[0] == pytest.approx(7 * 1440)  # 29 dias à frente, limitado a sete
    perto = e["ocorrido_em"].iloc[1] - timedelta(minutes=31)
    saida = com_macro(pd.DataFrame({"a": [1.0]}, index=pd.DatetimeIndex([perto])), divulgados_e_agenda(e, perto + timedelta(minutes=1)))
    assert saida["e_min_ate_macro"].iloc[0] == 30 and saida["e_macro_prox_60"].iloc[0] == 1 and saida["e_macro_prox_classe"].iloc[0] == 0


def test_treino_e_ao_vivo_veem_a_mesma_agenda():
    e = _eventos([0.1, 0.2, -0.1, 0.2, -0.2, 0.1, 0.3, -0.3])
    instante = e["ocorrido_em"].iloc[6] + timedelta(days=2)
    x = pd.DataFrame({"a": [1.0]}, index=pd.DatetimeIndex([instante - timedelta(minutes=1)]))
    treino, ao_vivo = com_macro(x, e), com_macro(x, divulgados_e_agenda(e, instante))
    pd.testing.assert_frame_equal(treino, ao_vivo)


def test_depois_da_agenda_conhecida_o_tempo_ate_o_evento_e_desconhecido():
    x = atributos_macro(pd.DataFrame([_evento(100)]), pd.date_range(INICIO, periods=150, freq="1min", tz="UTC"))
    assert x["e_min_ate_macro"].iloc[50] == 49 and np.isnan(x["e_min_ate_macro"].iloc[120])


def test_surpresa_usa_o_primeiro_numero_publicado():
    e = _eventos([0.1] * 8)
    revisao = e.iloc[[7]].assign(resultado=9.0, recebido_em=e["ocorrido_em"].iloc[7] + timedelta(days=30))
    primeiro = e.iloc[[7]].assign(recebido_em=e["ocorrido_em"].iloc[7] + timedelta(minutes=1))
    juntos = pd.concat([e.iloc[:7].assign(recebido_em=e["ocorrido_em"].iloc[:7]), revisao, primeiro]).assign(recebido_em=lambda t: pd.to_datetime(t["recebido_em"], utc=True))
    assert surpresas(juntos)["surpresa"].iloc[-1] == pytest.approx(0.1)


def test_ao_vivo_le_a_agenda_a_frente_de_hora_em_hora():
    datas = []

    def responder(pedido):
        datas.append(pedido.url.params["date"])
        return httpx.Response(200, json=RESPOSTA)

    ao_vivo = ResultadosAoVivo(FonteResultados(httpx.Client(transport=httpx.MockTransport(responder)), pausa=0))
    ao_vivo.coletar(AGORA)
    assert len(datas) == 9 and datas[-1] == "2026-11-12"
    datas.clear()
    ao_vivo.coletar(AGORA + timedelta(minutes=5))
    assert datas == ["2026-11-04", "2026-11-05"]
    datas.clear()
    ao_vivo.coletar(AGORA + timedelta(hours=1))
    assert len(datas) == 9


def _caso_agenda(com_efeito):
    g = np.random.default_rng(0)
    n = 4000
    indice = pd.date_range(INICIO, periods=n, freq="15min", tz="UTC")
    ate = np.arange(n) % 8 * 15.0  # um evento a cada 2 horas: janela grande o bastante para o mínimo de amostras por folha
    x = pd.DataFrame({"v_ruido": g.normal(size=n), "e_min_ate_macro": ate, "e_min_desde_macro": 1440 - ate, "e_macro_prox_60": (ate <= 60).astype(float), "e_macro_prox_24h": 1.0, "e_macro_prox_classe": 0.0, "e_ultima_surpresa_z": np.nan}, index=indice)
    y = pd.Series(g.normal(0, 0.3, n) + (2.0 * (ate <= 15) if com_efeito else 0.0), index=indice)
    return x, y


def test_ganho_da_agenda_acha_o_efeito_plantado():
    x, y = _caso_agenda(True)
    r = ganho_da_agenda(x, y, 15)
    assert r["evento_a_frente"]["ganho"] > 0.5 and r["evento_a_frente"]["ganho_ic95"][0] > 0


def test_ganho_da_agenda_nao_inventa_efeito_no_ruido():
    x, y = _caso_agenda(False)
    r = ganho_da_agenda(x, y, 15)
    assert r["tudo"]["ganho_ic95"][0] <= 0.02 and r["tudo"]["ganho"] < 0.05


def _velas(n=3000, passos=None):
    r = np.random.default_rng(0).normal(0, 0.0003, n) if passos is None else passos
    f = 100 * np.exp(np.cumsum(r))
    a = np.concatenate([[100.0], f[:-1]])
    return pd.DataFrame({"abertura": a, "maxima": np.maximum(a, f), "minima": np.minimum(a, f), "fechamento": f}, index=pd.date_range(INICIO, periods=n, freq="1min", tz="UTC", name="abertura_em"))


def _evento(minuto, z=1.0, id_="a", classe="inflacao_cpi"):
    return {"id": id_, "ocorrido_em": INICIO + pd.Timedelta(minutes=minuto), "classe": classe, "surpresa_z": z}


def test_reacao_entra_depois_do_atraso_e_mede_o_que_ja_andou():
    v = _velas(400)
    r = reacoes(pd.DataFrame([_evento(200)]), v, (5,)).iloc[0]
    assert r["retorno_5"] == pytest.approx(v["fechamento"].iloc[205] / v["abertura"].iloc[201] - 1)
    assert r["imediato"] == pytest.approx(v["abertura"].iloc[201] / v["abertura"].iloc[200] - 1)
    assert r["antes_60"] == pytest.approx(v["abertura"].iloc[200] / v["fechamento"].iloc[140] - 1)


def test_salto_no_minuto_do_evento_nao_conta_como_ganho():
    passos = np.zeros(400)
    passos[200] = 0.05  # o preço salta antes de qualquer um conseguir reagir
    v = _velas(400, passos)
    r = reacoes(pd.DataFrame([_evento(200)]), v, (5,)).iloc[0]
    assert r["retorno_5"] == pytest.approx(0, abs=1e-9)


def test_futuro_nao_muda_a_reacao_passada():
    v = _velas(1000)
    r = reacoes(pd.DataFrame([_evento(200)]), v, (5,))
    assert r["retorno_5"].iloc[0] == reacoes(pd.DataFrame([_evento(200)]), v.iloc[:300], (5,))["retorno_5"].iloc[0]


def test_resumo_acha_relacao_plantada_e_ignora_ruido():
    g = np.random.default_rng(1)
    z = g.normal(0, 1, 60)
    linhas = pd.DataFrame({"classe": "inflacao_cpi", "surpresa_z": z, "retorno_15": z * 0.002 + g.normal(0, 0.0005, 60), "amplitude_15": 0.01})
    ruido = pd.DataFrame({"classe": "pib", "surpresa_z": z, "retorno_15": g.normal(0, 0.002, 60), "amplitude_15": 0.01})
    t = resumir(pd.concat([linhas, ruido]), (15,)).set_index("classe")
    assert t.loc["inflacao_cpi", "p_ajustado"] < 0.01 and t.loc["inflacao_cpi", "mesmo_sinal"] > 0.8 and t.loc["inflacao_cpi", "retorno_fortes_alinhado_bps"] > 0
    assert t.loc["pib", "p_ajustado"] > 0.05


def test_poucos_eventos_nao_geram_conclusao():
    assert resumir(pd.DataFrame({"classe": "pib", "surpresa_z": [1.0, -1.0], "retorno_15": [0.01, -0.01], "amplitude_15": 0.01}), (15,)).empty


def test_volatilidade_em_torno_compara_com_o_mesmo_horario_sem_evento():
    passos = np.random.default_rng(0).normal(0, 0.0001, 1440 * 6)
    passos[1440 * 3 + 800:1440 * 3 + 815] *= 20
    v = _velas(1440 * 6, passos)
    e = pd.DataFrame({"ocorrido_em": [INICIO + pd.Timedelta(minutes=1440 * 3 + 799)]})
    assert volatilidade_em_torno(e, v, 15)["razao"] > 5


def test_atributos_macro_so_veem_o_que_ja_saiu():
    e = pd.DataFrame([_evento(100, 2.0), _evento(200, -1.0, "b")])
    indice = pd.date_range(INICIO, periods=300, freq="1min", tz="UTC")
    x = atributos_macro(e, indice)
    assert x["e_min_ate_macro"].iloc[89] == 10  # a vela 89 fecha no minuto 90
    assert np.isnan(x["e_ultima_surpresa_z"].iloc[98])
    assert x["e_ultima_surpresa_z"].iloc[99] == 2.0  # a vela 99 fecha no minuto do evento
    assert x["e_ultima_surpresa_z"].iloc[199] == -1.0 and x["e_min_desde_macro"].iloc[209] == 10


def test_atributos_macro_nao_mudam_com_eventos_futuros_de_resultado():
    indice = pd.date_range(INICIO, periods=150, freq="1min", tz="UTC")
    a = atributos_macro(pd.DataFrame([_evento(100, 2.0), _evento(200, -1.0, "b")]), indice)
    b = atributos_macro(pd.DataFrame([_evento(100, 2.0), _evento(200, 9.0, "b")]), indice)
    pd.testing.assert_series_equal(a["e_ultima_surpresa_z"], b["e_ultima_surpresa_z"])

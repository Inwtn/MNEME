"""Preços sintéticos para verificar regras; não medem desempenho da estratégia."""
import json
import unittest
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone

from mneme.estrategias.fimathe import RegraFimathe, VelaFimathe, simular
from mneme.fimathe import executar, ler_csv


REGRA = RegraFimathe(15, 4, "wicks", 10000, 1, 1.5, 100, .01, 100, .01, .2, .1, 2, 100, 2, 2, 0)
INICIO = datetime(2026, 1, 5, tzinfo=timezone.utc)


def velas():
    precos = [(100, 101, 99, 100)] * 4 + [(100, 104, 99.5, 104), (104, 105, 103, 104), (104, 120, 103, 113)]
    return [VelaFimathe(INICIO + timedelta(minutes=i * 15), *p) for i, p in enumerate(precos)]


class TestFimathe(unittest.TestCase):
    def test_regra_incompleta_observa_e_recusa_parametros_invalidos(self):
        self.assertIsNone(RegraFimathe.das_configuracoes({}))
        self.assertEqual(simular([], None)["status"], "observacao")
        for alteracao in ({"risk_pct": True}, {"spread": -1}, {"timeframe_minutes": 3}, {"min_lots": 200}, {"initial_balance": float("nan")}):
            with self.assertRaises(ValueError):
                RegraFimathe.das_configuracoes(asdict(REGRA) | alteracao)

    def test_cruzamento_confirmado_entra_so_na_abertura_seguinte_e_desconta_custos(self):
        dados = velas()
        self.assertIsNone(simular(dados[:5], REGRA)["position"])
        self.assertTrue(simular(dados[:5], REGRA)["pending_signal"])
        resultado = simular(dados, REGRA)
        t = resultado["trades"][0]
        self.assertEqual(t["opened_at"], dados[5].time.isoformat())
        self.assertAlmostEqual(t["entry"], 104.3)
        self.assertEqual(t["reason"], "alvo")
        self.assertLessEqual(t["planned_risk"], 100)
        self.assertAlmostEqual(resultado["metrics"]["balance"], 10000 + t["profit"])
        self.assertGreater(t["fees"], 0)
        self.assertEqual(resultado["metrics"]["accuracy_pct"], 100)
        json.dumps(resultado, allow_nan=False)

    def test_canal_corpos_e_canal_pavios_sao_diferentes(self):
        dados = velas()[:4]
        self.assertEqual(simular(dados, REGRA)["channel"], {"high": 101, "low": 99})
        self.assertEqual(simular(dados, replace(REGRA, marking="bodies"))["channel"], {"high": 100, "low": 100})

    def test_venda_usa_ask_para_saida(self):
        dados = [replace(v, open=200-v.open, high=200-v.low, low=200-v.high, close=200-v.close) for v in velas()]
        t = simular(dados, REGRA)["trades"][0]
        self.assertEqual(t["side"], "sell")
        self.assertEqual(t["reason"], "alvo")
        self.assertAlmostEqual(t["exit"], t["target"] + REGRA.slippage)

    def test_stop_primeiro_na_vela_ambigua_e_gap_piora_resultado(self):
        dados = velas()
        dados[5] = replace(dados[5], high=120, low=98)
        t = simular(dados[:6], REGRA)["trades"][0]
        self.assertEqual(t["reason"], "stop_ambiguo")
        self.assertLess(t["profit"], 0)
        dados = velas()
        dados[6] = replace(dados[6], open=90, high=92, low=89, close=91)
        gap = simular(dados, REGRA)["trades"][0]
        self.assertGreater(-gap["profit"], gap["planned_risk"])

    def test_lote_minimo_excessivo_e_sinal_atrasado_sao_bloqueados(self):
        result = simular(velas(), replace(REGRA, min_lots=2))
        self.assertFalse(result["trades"])
        self.assertIsNone(result["position"])
        self.assertIn("lote mínimo", result["decisions"][0]["motivo"])
        dados = velas()
        dados[5:] = [replace(v, time=v.time + timedelta(hours=1)) for v in dados[5:]]
        result = simular(dados, REGRA)
        self.assertFalse(result["trades"])
        self.assertIn("lacuna", result["decisions"][0]["motivo"])

    def test_limite_diario_trava_apos_saida_e_libera_a_meia_noite_brasilia(self):
        dados = velas()
        dados[5] = replace(dados[5], high=120, low=98)
        dados.append(VelaFimathe(datetime(2026, 1, 5, 3, tzinfo=timezone.utc), 100, 101, 99, 100))
        result = simular(dados, replace(REGRA, daily_loss_limit_pct=.1))
        self.assertTrue(result["curve"][5]["entries_blocked"])
        self.assertFalse(result["curve"][-1]["entries_blocked"])
        self.assertEqual(len(result["trades"]), 1)

    def test_futuro_nao_altera_passado_e_nao_reentra_na_remarcacao(self):
        dados = velas()
        prefixo = simular(dados[:6], REGRA)
        completo = simular(dados, REGRA)
        self.assertEqual(prefixo["curve"], completo["curve"][:6])
        self.assertFalse(completo["pending_signal"])
        self.assertEqual(simular(dados[:4], REGRA)["metrics"]["accuracy_pct"], None)

    def test_csv_fuso_explicito_mt5_e_iso(self):
        r = replace(REGRA, csv_utc_offset_minutes=-180)
        texto = "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\n" + "\n".join(f"2026.01.05\t00:{i*15:02}:00\t100\t101\t99\t100" for i in range(4)) + "\n2026.01.05\t01:00:00\t100\t104\t99\t104"
        self.assertEqual(ler_csv(texto, r)[0].time.hour, 3)
        texto = "time,open,high,low,close\n" + "\n".join(f"{v.time.isoformat()},{v.open},{v.high},{v.low},{v.close}" for v in velas())
        config = {"schema": 1, "strategy": "fimathe", "symbol": "XAUUSD", "parameters": asdict(REGRA)}
        resultado = executar(config, texto, "Fixture sintética de teste")
        self.assertEqual(resultado["source"]["bars"], 7)
        self.assertEqual(len(resultado["source"]["sha256"]), 64)
        with self.assertRaises(ValueError):
            ler_csv(texto, r, agora=INICIO)

    def test_recusa_duplicatas_ohlc_incoerente_e_outro_intervalo(self):
        dados = velas()
        for invalido in (dados[:4] + [dados[3]], [replace(dados[0], low=102)] + dados[1:], [dados[0], replace(dados[1], time=INICIO+timedelta(minutes=1))] + dados[2:]):
            with self.assertRaises(ValueError):
                simular(invalido, REGRA)


class TestFimatheLaboratorio(unittest.TestCase):
    def setUp(self):
        import pandas as pd
        self.config = {"schema": 1, "strategy": "fimathe", "symbol": "XAUUSD", "parameters": asdict(REGRA)}
        linhas = []
        indices = []
        for v in velas():
            for i in range(15):
                linhas.append((v.open, v.high, v.low, v.close, 1))
                indices.append(v.time + timedelta(minutes=i))
        self.v = pd.DataFrame(linhas, index=pd.DatetimeIndex(indices), columns=["abertura", "maxima", "minima", "fechamento", "volume"])

    def test_catalogo_comum_inclui_fimathe_sem_inventar_parametros(self):
        from mneme.setups import SETUPS, NOME_FIMATHE, setups_configurados
        self.assertIn(NOME_FIMATHE, SETUPS)
        self.assertEqual(int(SETUPS[NOME_FIMATHE](self.v).sum()), 0)
        self.assertNotIn(NOME_FIMATHE, setups_configurados())
        self.assertNotIn(NOME_FIMATHE, setups_configurados(self.config, "BTCUSDT"))
        self.assertIn(NOME_FIMATHE, setups_configurados(self.config, "XAUUSD"))

    def test_sinal_comum_so_aparece_apos_periodo_completo_e_sem_vazamento(self):
        from mneme.laboratorio.fimathe import sinais, preparar
        from mneme.laboratorio.backtest import olha_o_futuro
        self.assertEqual(len(preparar(self.v.iloc[:74], REGRA)), 4)
        sinal = sinais(self.v, REGRA)
        self.assertEqual(list(sinal[sinal != 0].index), [self.v.index[74]])
        self.assertEqual(olha_o_futuro(lambda v: sinais(v, REGRA), self.v), [])
        self.assertEqual(sinais(self.v.drop(self.v.index[70]), REGRA).abs().sum(), 0)

    def test_posicao_mantem_stop_alvo_custos_e_lote_da_fimathe(self):
        from mneme.laboratorio.fimathe import operacoes
        resultado = operacoes(self.v, REGRA)
        self.assertEqual(len(resultado), 1)
        self.assertAlmostEqual(resultado.iloc[0]["retorno"], 140.58 / 10000)

    def test_runner_comum_registra_fimathe_sem_trocar_regra_por_atr(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from mneme.laboratorio.__main__ import estudar_spot
        from mneme.laboratorio.backtest import CustoSpot
        from mneme.laboratorio.registro import Registro
        from mneme.setups import NOME_FIMATHE, fimathe
        class Armazem:
            def __init__(self, v): self.v = v
            def ler(self, par): return self.v
        with tempfile.TemporaryDirectory() as temp, patch("builtins.print"), patch.dict("mneme.setups.SETUPS", {NOME_FIMATHE: fimathe}, clear=True):
            pasta = Path(temp)
            registro = Registro(pasta / "experimentos.jsonl", commit="teste")
            estudar_spot(Armazem(self.v), registro, ["XAUUSD"], 999, 999, 1, CustoSpot(.5, .5), pasta, self.config)
            experimento = registro.todos()[0]
            self.assertEqual(experimento["nome"], NOME_FIMATHE)
            self.assertEqual(experimento["familia"], "setups_spot")
            self.assertEqual(experimento["parametros"]["fimathe"], self.config)
            self.assertEqual(experimento["resultado"]["execucao"], "risco_configurado")
            self.assertEqual(experimento["resultado"]["operacoes"], 1)

    def test_catalogo_do_painel_e_o_mesmo_dos_experimentos(self):
        from pathlib import Path
        from mneme.laboratorio.catalogo import catalogo
        publicado = json.loads((Path(__file__).resolve().parents[2] / "public/assets/laboratorio-catalogo.json").read_text(encoding="utf-8"))
        self.assertEqual(publicado, catalogo())

    def test_resultado_sem_medicao_exporta_json_valido(self):
        import tempfile
        from pathlib import Path
        from mneme.laboratorio.__main__ import _salvar
        with tempfile.TemporaryDirectory() as temp:
            _salvar(Path(temp), "sem_amostra", [{"acerto": float("nan"), "fator": float("inf")}])
            self.assertEqual(json.loads((Path(temp) / "sem_amostra.json").read_text()), [{"acerto": None, "fator": None}])


if __name__ == "__main__":
    unittest.main()

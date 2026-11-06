"""O script do gráfico carrega os pesos certos e as técnicas valem o que o laboratório mede."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mneme.laboratorio.confluencia import grade_de_sinais
from mneme.motor.pine import CURTOS, TECNICAS, gerar_pine


def _modelo(pesos=(0.1, 0.2, -0.3, 0.4, -0.5, 0.6)):
    return {"tecnicas": list(TECNICAS), "pesos": list(pesos), "intercepto": -0.01, "corte": 0.04, "evidencia": {"operacoes": 900, "acerto": 0.5123}}


def test_script_tem_o_ativo_os_pesos_na_ordem_e_opera_so_para_frente():
    s = gerar_pine({"XAUUSD": _modelo()}, "2026-11-06T18:00:00+00:00")
    assert '"XAUUSD" => array.from(0.10000, 0.20000, -0.30000, 0.40000, -0.50000, 0.60000, -0.01000, 0.04000, 0.5123, 900)' in s
    assert 'timestamp("2026-11-06T18:00:00+00:00")' in s and "time >= inicio" in s and "__" not in s.replace("__INICIO__", "")


def test_a_ordem_dos_pesos_segue_as_tecnicas_e_nao_o_arquivo():
    m = _modelo()
    m["tecnicas"], m["pesos"] = list(reversed(m["tecnicas"])), list(reversed(m["pesos"]))
    assert "array.from(0.10000, 0.20000, -0.30000" in gerar_pine({"EURUSD": m}, "2026-11-06T18:00:00+00:00")


def test_ativo_sem_modelo_nao_opera():
    s = gerar_pine({"XAUUSD": _modelo()}, "2026-11-06T18:00:00+00:00")
    assert "=> array.new<float>()" in s and "liberado = conhecido and confiante" in s


def test_nomes_batem_com_as_tecnicas_e_existem_no_laboratorio():
    assert len(CURTOS) == len(TECNICAS)
    g = np.random.default_rng(0)
    f = 100 * np.exp(np.cumsum(g.normal(0, 0.0008, 6000)))
    a = np.concatenate([[100.0], f[:-1]])
    v = pd.DataFrame({"abertura": a, "maxima": np.maximum(a, f) + 0.02, "minima": np.minimum(a, f) - 0.02, "fechamento": f, "volume": 10.0, "negocios": 10, "volume_comprador": 5.0}, index=pd.date_range("2026-01-01", periods=6000, freq="1min", tz="UTC", name="abertura_em"))
    assert set(TECNICAS) <= set(grade_de_sinais(v, 5).columns)


def test_nao_existe_ordem_real_nem_chamada_externa_no_script():
    s = gerar_pine({"XAUUSD": _modelo()}, "2026-11-06T18:00:00+00:00")
    assert "alert(" not in s and "webhook" not in s.lower() and "request." not in s

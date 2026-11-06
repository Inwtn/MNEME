"""Regressão entre módulos: o robô de seguir traders e cada serviço do compose continuam importando. Foi o que faltou quando a carteira foi sobrescrita."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).parent.parent
SERVICOS = sorted(set(re.findall(r'"-m",\s*"(mneme[\w.]*)"', (RAIZ / "compose.yaml").read_text(encoding="utf-8"))))
ROBO_ORIGINAL = ["mneme.__main__", "mneme.ciclo", "mneme.telegram", "mneme.carteira", "mneme.estrategias.seguir_traders"]


def test_compose_tem_servicos_e_o_motor():
    assert "mneme.carteira_tecnicas" in SERVICOS and "mneme.motor" in SERVICOS


@pytest.mark.parametrize("modulo", SERVICOS + ROBO_ORIGINAL)
def test_modulo_importa(modulo):
    alvo = importlib.import_module(modulo if modulo in ROBO_ORIGINAL or (RAIZ / (modulo.replace(".", "/") + ".py")).exists() else modulo + ".__main__")
    assert alvo is not None


def test_controles_de_risco_do_robo_original_continuam_la():
    from mneme.carteira import Carteira, LimitesDia, bloqueio_do_dia, dia_brasilia

    assert all([Carteira, dia_brasilia]) and bloqueio_do_dia(LimitesDia(1, 1), -2) is not None

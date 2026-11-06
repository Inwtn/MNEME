"""A identidade do produto não pode encolher de novo sem ninguém ver. Roda onde os documentos existem."""

from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
MERCADOS = ("forex", "ouro", "bitcoin", "ethereum", "solana", "quotex", "jupiter")
ENCOLHEM = ("um robô só", "bot de copy trading")


def _ler(caminho: str) -> str:
    arquivo = RAIZ / caminho
    if not arquivo.exists():
        pytest.skip(f"{caminho} não veio nesta cópia")
    return arquivo.read_text(encoding="utf-8").lower()


@pytest.mark.parametrize("caminho", ["docs/PRODUCT_CHARTER.md", "README.md"])
def test_documento_central_cita_todos_os_mercados(caminho):
    texto = _ler(caminho)
    assert [m for m in MERCADOS if m not in texto] == []


def test_definicao_oficial_diz_o_que_o_produto_e_e_nao_e():
    texto = _ler("docs/PRODUCT_CHARTER.md")
    for trecho in ("inteligência artificial financeira híbrida", "deep learning", "somente um gerador de sinais", "capacidade operacional"):
        assert trecho in texto


@pytest.mark.parametrize("caminho", ["README.md", "docs/robo.md", "docs/design.md", "robo/LEIA-ME.md", "docs/architecture/SYSTEM_OVERVIEW.md", "package.json"])
def test_nenhum_documento_encolhe_o_produto(caminho):
    texto = _ler(caminho)
    assert [t for t in ENCOLHEM if t in texto] == []


def test_o_robo_de_seguir_traders_continua_documentado():
    assert "seguir" in _ler("robo/LEIA-ME.md") and "maioria" in _ler("docs/robo.md")


def test_charter_separa_objetivo_de_estado_e_nao_marca_o_que_falta_como_pronto():
    estado = _ler("docs/PRODUCT_CHARTER.md").split("## 10.")[1]
    for capacidade in ("deep learning", "langgraph", "harmonic patterns", "on-chain"):
        linhas = [l for l in estado.splitlines() if capacidade in l]
        assert linhas and all("não implementado" in l for l in linhas), capacidade


@pytest.mark.parametrize("caminho", ["CLAUDE.md", "GEMINI.md", "AGENTS.md"])
def test_instrucoes_das_ias_apontam_para_o_charter(caminho):
    assert "docs/product_charter.md" in _ler(caminho)


@pytest.mark.parametrize("caminho", ["docs/architecture/ROADMAP.md", "README.md", "docs/architecture/SYSTEM_OVERVIEW.md", "robo/LEIA-ME.md"])
def test_documentos_apontam_para_o_charter(caminho):
    assert "product_charter.md" in _ler(caminho)

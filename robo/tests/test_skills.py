"""As skills do MNEME ficam curtas, sem scripts nem ganchos, obedecem ao Charter e não autorizam operação. Roda onde os arquivos existem."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SKILLS = RAIZ / ".claude" / "skills"
PASTAS = sorted(SKILLS.glob("mneme-*")) if SKILLS.exists() else []
PROIBIDOS = ("extremely-important", "ignore previous", "ignore todas", "não é negociável", "you do not have a choice", "private_key", "curl |", "sessionstart", "garantido", "sem aprovação do risk", "pode operar em real", "dinheiro real liberado")


def _partes(pasta: Path) -> tuple[dict, str]:
    texto = (pasta / "SKILL.md").read_text(encoding="utf-8")
    bloco = re.match(r"---\n(.*?)\n---\n(.*)", texto, re.S)
    assert bloco, f"{pasta.name}: sem cabeçalho"
    campos = dict(linha.split(": ", 1) for linha in bloco.group(1).splitlines())
    return campos, bloco.group(2)


def test_primeiro_lote_existe():
    if not SKILLS.exists():
        pytest.skip(".claude/skills não veio nesta cópia")
    assert {p.name for p in PASTAS} >= {"mneme-verificacao", "mneme-auditoria-backtest", "mneme-revisao-injecao"}


@pytest.mark.parametrize("pasta", PASTAS, ids=lambda p: p.name)
def test_formato_e_tamanho(pasta):
    campos, corpo = _partes(pasta)
    assert campos["name"] == pasta.name and 30 < len(campos["description"]) <= 300 and campos["description"].startswith("Use ")
    assert len(corpo.splitlines()) <= 100


@pytest.mark.parametrize("pasta", PASTAS, ids=lambda p: p.name)
def test_so_texto_sem_scripts_nem_ganchos(pasta):
    assert [a.name for a in pasta.rglob("*") if a.is_file()] == ["SKILL.md"]


@pytest.mark.parametrize("pasta", PASTAS, ids=lambda p: p.name)
def test_obedece_ao_charter_e_da_credito(pasta):
    _campos, corpo = _partes(pasta)
    assert "docs/PRODUCT_CHARTER.md" in corpo and "## Crédito" in corpo and "github.com/" in corpo


@pytest.mark.parametrize("pasta", PASTAS, ids=lambda p: p.name)
def test_sem_frases_que_passam_por_cima_das_regras(pasta):
    texto = (pasta / "SKILL.md").read_text(encoding="utf-8").lower().replace("`curl | sh`", "")
    assert [p for p in PROIBIDOS if p in texto] == []


@pytest.mark.parametrize("pasta", PASTAS, ids=lambda p: p.name)
def test_esta_no_catalogo(pasta):
    catalogo = RAIZ / "docs" / "skills" / "SKILL_CATALOG.md"
    if not catalogo.exists():
        pytest.skip("catálogo não veio nesta cópia")
    assert f"`{pasta.name}`" in catalogo.read_text(encoding="utf-8")


def test_nomes_citados_na_auditoria_existem_no_codigo():
    """A skill não pode mandar usar função que não existe, nem continuar citando uma que foi renomeada."""
    from mneme.laboratorio import avaliacao, backtest, horizontes, robustez, validacao
    from mneme.laboratorio.registro import Registro

    assert all(hasattr(m, n) for m, n in [(validacao, "dobras_walk_forward"), (avaliacao, "selecionar_com_passado"), (backtest, "placebo_direcao"), (robustez, "estressar"), (robustez, "intervalo_por_dias"), (validacao, "holm"), (validacao, "prob_sobreajuste"), (validacao, "sharpe_deflacionado"), (horizontes, "medir_operacoes"), (Registro, "anotar")])


def test_nomes_citados_na_revisao_existem_no_codigo():
    from mneme import analista

    assert all(hasattr(analista, n) for n in ("verificar_leitura", "ler_noticia", "responder", "ATAQUES", "avaliar_ataques"))


ORIGINAIS = ("systematic-debugging", "test-driven-development", "context-engineering", "doubt-driven-development", "observability-and-instrumentation", "backtest-expert", "market-microstructure", "regime-detection", "slippage-modeling", "whale-tracking", "trade-journal")


@pytest.mark.parametrize("nome", ORIGINAIS)
def test_original_mantem_licenca_e_origem_sem_ganchos(nome):
    pasta = SKILLS / nome
    if not pasta.exists():
        pytest.skip(f"{nome} não veio nesta cópia")
    assert "MIT" in (pasta / "LICENSE").read_text(encoding="utf-8") and "/" in (pasta / "ORIGEM.txt").read_text(encoding="utf-8")
    assert not [a for a in pasta.rglob("*") if a.name in ("hooks.json", "plugin.json", ".mcp.json")]
    catalogo = RAIZ / "docs" / "skills" / "SKILL_CATALOG.md"
    if catalogo.exists():
        assert f"`{nome}`" in catalogo.read_text(encoding="utf-8")


@pytest.mark.parametrize("nome", ORIGINAIS)
def test_original_nao_pede_chave_privada_nem_passa_por_cima_das_regras(nome):
    pasta = SKILLS / nome
    if not pasta.exists():
        pytest.skip(f"{nome} não veio nesta cópia")
    texto = "\n".join(a.read_text(encoding="utf-8", errors="ignore").lower() for a in pasta.rglob("*") if a.is_file())
    assert "private_key" not in texto and "keypair" not in texto and "ignore previous" not in texto

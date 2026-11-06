"""Risk Engine: determinístico e sem rede. Na dúvida não abre. Só este módulo cria a Aprovacao que o executor exige, e o tamanho nunca sobe depois de perda."""

from __future__ import annotations

from dataclasses import dataclass, fields

from ..carteira import LimitesDia, bloqueio_do_dia
from .modalidades import Limites

_SO_O_RISCO_CRIA = object()


@dataclass(frozen=True)
class Estado:
    """A situação da carteira desta estratégia, lida do diário no momento da decisão."""
    kill_switch: bool
    idade_dados_min: float
    chave_repetida: bool
    aberta_na_estrategia: bool
    abertas_total: int
    operacoes_hoje: int
    retorno_dia_pct: float
    perdas_seguidas: int
    drawdown_pct: float


class Aprovacao:
    def __init__(self, chave: str, tamanho: float, _token: object = None):
        if _token is not _SO_O_RISCO_CRIA:
            raise PermissionError("Só o Risk Engine aprova uma operação.")
        self.chave, self.tamanho = chave, tamanho


def avaliar(chave: str, estado: Estado, limites: Limites, tamanho_fixo: float) -> tuple[Aprovacao | None, tuple[str, ...]]:
    """Devolve a aprovação ou todos os motivos da recusa. `tamanho_fixo` vem da configuração: não depende do resultado anterior, então não existe martingale."""
    vazios = [c.name for c in fields(limites) if getattr(limites, c.name) is None]
    motivos = [f"limite sem valor: {', '.join(vazios)}"] if vazios else []
    if estado.kill_switch:
        motivos.append("kill switch ligado")
    if estado.chave_repetida:
        motivos.append("operação repetida")
    if estado.aberta_na_estrategia:
        motivos.append("esta estratégia já tem operação aberta")
    if not vazios:
        if estado.idade_dados_min > limites.idade_maxima_dados_min:
            motivos.append(f"dados velhos: {estado.idade_dados_min:.1f} min")
        if estado.abertas_total >= limites.max_simultaneas_total:
            motivos.append("limite de operações simultâneas")
        if estado.operacoes_hoje >= limites.max_operacoes_dia:
            motivos.append("limite de operações do dia")
        if estado.perdas_seguidas >= limites.max_perdas_seguidas:
            motivos.append(f"{estado.perdas_seguidas} perdas seguidas: pausa até o dia seguinte")
        if estado.drawdown_pct >= limites.drawdown_max_pct:
            motivos.append(f"drawdown de {estado.drawdown_pct:.1f}%: para até revisão humana")
        dia = bloqueio_do_dia(LimitesDia(limites.meta_dia_pct, limites.perda_dia_pct), estado.retorno_dia_pct)
        if dia:
            motivos.append(dia)
    if tamanho_fixo <= 0:
        motivos.append("tamanho sem valor")
    if motivos:
        return None, tuple(motivos)
    return Aprovacao(chave, tamanho_fixo, _SO_O_RISCO_CRIA), ()

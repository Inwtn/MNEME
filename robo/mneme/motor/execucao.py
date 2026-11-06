"""Execução. Hoje só existe o simulado: nenhuma ordem sai daqui. Um executor real precisa de autorização do dono e de um adaptador novo."""

from __future__ import annotations

from typing import Protocol

from .risco import Aprovacao


class Executor(Protocol):
    def executar(self, aprovacao: Aprovacao, **registro) -> bool: ...


class ExecutorPaper:
    """Grava a operação no diário. A apuração usa as velas depois, com a mesma regra para operadas e para sombra."""

    def __init__(self, diario):
        self.diario = diario

    def executar(self, aprovacao: Aprovacao, **registro) -> bool:
        if not isinstance(aprovacao, Aprovacao):
            raise PermissionError("O executor só aceita aprovação do Risk Engine.")
        return self.diario.registrar(**registro, tipo="operada", tamanho=aprovacao.tamanho)


def criar_executor(modo: str, diario) -> Executor:
    if modo != "paper":
        raise ValueError(f"Modo '{modo}' sem executor: só existe o simulado, e a execução real exige autorização do dono.")
    return ExecutorPaper(diario)

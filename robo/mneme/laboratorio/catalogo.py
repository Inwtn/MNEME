"""Catálogo único para o laboratório e a lista de estratégias do painel."""
from ..setups import SETUPS
from .modelos import MODELOS


def catalogo() -> dict:
    return {"schema": 1, "strategies": [
        *({"id": nome, "name": nome, "kind": "setup"} for nome in SETUPS),
        *({"id": nome, "name": nome, "kind": "modelo"} for nome in MODELOS),
    ]}

"""Linha de comando dos dados de mercado.

    uv run python -m mneme.dados importar --meses 24
    uv run python -m mneme.dados coletar
    uv run python -m mneme.dados resumo
    uv run python -m mneme.dados ler BTCUSDT --tempo 15min
    uv run python -m mneme.dados fluxo
    uv run python -m mneme.dados importar-derivativos --meses 24
    uv run python -m mneme.dados resumo-fluxo
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import logging
import os
import signal

import pandas as pd

from ..config import PASTA_DADOS
from ..fluxo import lacunas_livro, trades_faltando
from ..leitura import ler_mercado
from .armazem import ArmazemVelas, agora_utc, dias_atras
from .binance import FonteBinance
from .coleta import Coletor
from .coleta_fluxo import ColetorFluxo, importar_derivativos
from .eventos import ArmazemEventos


async def rodar_fluxo(pares: list[str], raiz: str) -> None:
    """Coleta até receber o sinal de desligar; `docker stop` grava o que está em memória antes de sair."""
    parar = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sinal in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sinal, parar.set)
        except NotImplementedError:  # Windows
            pass
    await ColetorFluxo(pares, ArmazemEventos(raiz)).rodar(parar)


def resumo_fluxo(armazem: ArmazemEventos, pares: list[str]) -> None:
    agora = agora_utc()
    hoje = f"{agora:%Y-%m-%d}"
    inicio_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    for par in pares:
        for tipo in ("trades", "livro", "derivativos", "liquidacoes", "funding", "open_interest"):
            tamanhos = armazem.tamanho_por_dia(tipo, par)
            if not tamanhos:
                continue
            eventos = armazem.ler(tipo, par, inicio=inicio_dia)
            info = {"par": par, "tipo": tipo, "dias": len(tamanhos), "mb_total": round(sum(tamanhos.values()) / 1e6, 2),
                    "mb_hoje": round(tamanhos.get(hoje, 0) / 1e6, 2), "eventos_hoje": len(eventos)}
            if not eventos.empty and "recebido_em" in eventos and eventos["recebido_em"].notna().any():
                vivos = eventos[eventos["recebido_em"].notna()]
                horas = (vivos["ocorrido_em"].max() - vivos["ocorrido_em"].min()).total_seconds() / 3600
                if horas > 0:
                    info["horas_coletadas"] = round(horas, 2)
                    info["mb_por_dia_estimado"] = round(tamanhos.get(hoje, 0) / 1e6 / horas * 24, 1)
                if tipo == "trades":
                    info["trades_faltando"] = trades_faltando(eventos)
                if tipo == "livro":
                    info["lacunas_livro"] = len(lacunas_livro(eventos))
            print(json.dumps(info, ensure_ascii=False))


def _meses(quantos: int) -> list[tuple[int, int]]:
    """Os `quantos` meses fechados mais recentes, do mais antigo para o mais novo."""
    atual = pd.Timestamp(agora_utc()).to_period("M")
    return [((atual - i).year, (atual - i).month) for i in range(quantos, 0, -1)]


def importar(armazem: ArmazemVelas, pares: list[str], meses: int) -> None:
    fonte = FonteBinance()
    for par in pares:
        for ano, mes in _meses(meses):
            print(f"{par} {ano}-{mes:02d}: {armazem.gravar(par, fonte.arquivo_mes(par, ano, mes), agora_utc())} velas novas", flush=True)
    # O restante, do início do mês atual até agora, vem do REST.
    Coletor(pares, armazem, fonte).recuperar()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="mneme.dados")
    parser.add_argument("--pares", default=os.getenv("MNEME_PARES_VELAS", "BTCUSDT,ETHUSDT,SOLUSDT"))
    parser.add_argument("--raiz", default=os.getenv("MNEME_DADOS_MERCADO", str(PASTA_DADOS / "mercado")))
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("importar").add_argument("--meses", type=int, default=24)
    sub.add_parser("coletar")
    sub.add_parser("resumo")
    sub.add_parser("fluxo")
    sub.add_parser("resumo-fluxo")
    sub.add_parser("importar-derivativos").add_argument("--meses", type=int, default=24)
    leitura = sub.add_parser("ler")
    leitura.add_argument("par")
    leitura.add_argument("--tempo", default="15min")
    leitura.add_argument("--dias", type=int, default=14)
    args = parser.parse_args()
    pares = [p.strip().upper() for p in args.pares.split(",") if p.strip()]
    armazem = ArmazemVelas(args.raiz)
    if args.comando == "importar":
        importar(armazem, pares, args.meses)
    elif args.comando == "coletar":
        asyncio.run(Coletor(pares, armazem).rodar())
    elif args.comando == "fluxo":
        asyncio.run(rodar_fluxo(pares, args.raiz))
    elif args.comando == "resumo-fluxo":
        resumo_fluxo(ArmazemEventos(args.raiz), pares)
    elif args.comando == "importar-derivativos":
        print(json.dumps(importar_derivativos(ArmazemEventos(args.raiz), pares, args.meses)))
    elif args.comando == "resumo":
        for par in pares:
            print(json.dumps(armazem.resumo(par), ensure_ascii=False))
    else:
        velas = armazem.ler(args.par.upper(), inicio=dias_atras(args.dias))
        print(json.dumps(dataclasses.asdict(ler_mercado(velas, args.par.upper(), args.tempo)), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

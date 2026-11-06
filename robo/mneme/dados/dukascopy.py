"""Histórico de 1 minuto de moedas e ouro, para o laboratório. Só importa: não é coleta ao vivo.

Forex não tem agressão por lado nesta fonte: `volume_comprador` fica na metade do volume, o que zera o delta. Por isso as colunas f_delta não têm sentido nesses ativos.
Cotação BID, sem o spread da corretora. Os termos de uso da fonte estão nas pendências externas.

    python -m mneme.dados.dukascopy --pares EURUSD,GBPUSD,USDJPY,XAUUSD --meses 24
"""

from __future__ import annotations

import argparse
import json
import lzma
import os
import struct
import time
from datetime import date, datetime, timedelta, timezone

import httpx
import pandas as pd

from ..config import PASTA_DADOS
from .armazem import ArmazemVelas, agora_utc
from .velas import linha, tabela

URL = "https://datafeed.dukascopy.com/datafeed/{par}/{ano}/{mes:02d}/{dia:02d}/BID_candles_min_1.bi5"
ESCALAS = {"EURUSD": 1e5, "GBPUSD": 1e5, "AUDUSD": 1e5, "NZDUSD": 1e5, "USDCAD": 1e5, "USDCHF": 1e5, "EURGBP": 1e5, "USDJPY": 1e3, "EURJPY": 1e3, "GBPJPY": 1e3, "XAUUSD": 1e3}
REGISTRO = struct.Struct(">5if")  # segundos no dia, abertura, fechamento, mínima, máxima, volume
ORIGEM = "dukascopy"


def url_do_dia(par: str, dia: date) -> str:
    """Na URL os meses começam em zero: janeiro é 00."""
    return URL.format(par=par, ano=dia.year, mes=dia.month - 1, dia=dia.day)


def ler_dia(comprimido: bytes, par: str, dia: date) -> list[dict]:
    """Minutos sem nenhum volume são mercado fechado, com o preço repetido, e ficam de fora: não são candles de verdade."""
    if not comprimido:
        return []
    escala = ESCALAS[par]
    bruto = lzma.decompress(comprimido)
    inicio = int(datetime(dia.year, dia.month, dia.day, tzinfo=timezone.utc).timestamp())
    linhas = []
    for segundos, abertura, fechamento, minima, maxima, volume in REGISTRO.iter_unpack(bruto):
        if volume > 0:
            linhas.append(linha((inicio + segundos) * 1000, abertura / escala, maxima / escala, minima / escala, fechamento / escala, float(volume), 0.0, 0, float(volume) / 2, None, ORIGEM))
    return linhas


def baixar_dia(cliente: httpx.Client, par: str, dia: date, tentativas: int = 6, espera: float = 5.0) -> list[dict] | None:
    """A fonte limita o ritmo com 503. Espera e tenta de novo; `None` quer dizer que o dia falhou e pode ser buscado depois."""
    for tentativa in range(tentativas):
        try:
            r = cliente.get(url_do_dia(par, dia))
            if r.status_code == 404:
                return []
            if r.status_code == 200:
                return ler_dia(r.content, par, dia)
        except httpx.HTTPError:
            pass
        time.sleep(espera * (tentativa + 1))
    return None


def importar(armazem: ArmazemVelas, par: str, inicio: date, fim: date, cliente: httpx.Client, pausa: float = 1.0) -> dict:
    d, novas, dias, falhas = inicio, 0, 0, []
    while d <= fim:
        if d.weekday() != 5:  # sábado o mercado está fechado o dia inteiro
            linhas = baixar_dia(cliente, par, d)
            if linhas is None:
                falhas.append(str(d))
            elif linhas:
                novas += armazem.gravar(par, tabela(linhas), agora_utc())
                dias += 1
            time.sleep(pausa)
        d += timedelta(days=1)
    return {"par": par, "dias": dias, "velas_novas": novas, "dias_com_falha": falhas}


def main() -> None:
    parser = argparse.ArgumentParser(prog="mneme.dados.dukascopy")
    parser.add_argument("--pares", default="EURUSD,GBPUSD,USDJPY,XAUUSD")
    parser.add_argument("--meses", type=int, default=24)
    parser.add_argument("--raiz", default=os.getenv("MNEME_DADOS_MERCADO", str(PASTA_DADOS / "mercado")))
    args = parser.parse_args()
    fim = agora_utc().date() - timedelta(days=1)
    inicio = fim - timedelta(days=args.meses * 31)
    armazem = ArmazemVelas(args.raiz)
    with httpx.Client(timeout=30, headers={"user-agent": "Mozilla/5.0"}) as cliente:
        for par in args.pares.split(","):
            print(json.dumps(importar(armazem, par.strip().upper(), inicio, fim, cliente)), flush=True)


if __name__ == "__main__":
    main()

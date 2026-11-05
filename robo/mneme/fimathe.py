"""Importação de CSV para a Fimathe no laboratório comum do MNEME."""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime, timedelta, timezone

from .estrategias.fimathe import RegraFimathe, VelaFimathe, simular


def ler_csv(texto: str, regra: RegraFimathe, agora: datetime | None = None) -> list[VelaFimathe]:
    texto = texto.lstrip("\ufeff")
    cabecalho = texto.splitlines()[0] if texto.strip() else ""
    separador = "\t" if "\t" in cabecalho else ";" if ";" in cabecalho else ","
    linhas = csv.DictReader(io.StringIO(texto), delimiter=separador)
    if not linhas.fieldnames:
        raise ValueError("CSV vazio ou sem cabeçalho.")
    linhas.fieldnames = [k.strip().lower().strip("<>") for k in linhas.fieldnames]
    if not {"open", "high", "low", "close", "time"}.issubset(linhas.fieldnames):
        raise ValueError("Use time,open,high,low,close ou DATE/TIME/OHLC do MT5.")
    velas = []
    agora = agora or datetime.now(timezone.utc)
    fuso = timezone(timedelta(minutes=regra.csv_utc_offset_minutes))
    for numero, linha in enumerate(linhas, 2):
        if len(velas) >= 100_000:
            raise ValueError("Use até 100.000 velas por teste.")
        try:
            raw = linha["time"].strip()
            if "date" in linha:
                raw = linha["date"].strip().replace(".", "-") + "T" + raw
            try:
                quando = datetime.fromtimestamp(float(raw), timezone.utc)
            except ValueError:
                quando = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if quando.tzinfo is None:
                    quando = quando.replace(tzinfo=fuso)
            quando = quando.astimezone(timezone.utc)
            if quando + timedelta(minutes=regra.timeframe_minutes) > agora:
                raise ValueError("vela ainda aberta ou no futuro")
            precos = [float(linha[k].strip().replace(",", ".")) for k in ("open", "high", "low", "close")]
            velas.append(VelaFimathe(quando, *precos))
        except (ValueError, TypeError, KeyError, OverflowError, OSError) as erro:
            raise ValueError(f"Linha {numero} inválida: {erro}.") from erro
    if len(velas) < regra.channel_candles + 1:
        raise ValueError("Histórico insuficiente para formar o canal e avaliar um rompimento.")
    return velas


def executar(config: dict, texto: str, fonte: str, agora: datetime | None = None) -> dict:
    if config.get("schema") != 1 or config.get("strategy") != "fimathe" or config.get("symbol") != "XAUUSD":
        raise ValueError("Use a configuração Fimathe XAUUSD exportada pelo MNEME.")
    if not isinstance(config.get("parameters"), dict):
        raise ValueError("Configuração sem parâmetros.")
    regra = RegraFimathe.das_configuracoes(config["parameters"])
    if regra is None:
        return simular([], None)
    if not isinstance(fonte, str) or not fonte.strip() or len(fonte) > 120:
        raise ValueError("Identifique a fonte do CSV em até 120 caracteres.")
    velas = ler_csv(texto, regra, agora)
    resultado = simular(velas, regra)
    resultado.update(schema=1, symbol="XAUUSD", source={"name": fonte, "sha256": hashlib.sha256(texto.encode()).hexdigest(),
                     "bars": len(velas), "start": velas[0].time.isoformat(), "end": velas[-1].time.isoformat()})
    return resultado

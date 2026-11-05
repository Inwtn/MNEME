"""Calendário econômico. As reuniões do FOMC têm histórico; os demais eventos e as previsões se acumulam a partir da coleta."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

URL_FOMC = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
URL_SEMANA = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
AGENTE = {"user-agent": "Mozilla/5.0 (compatible; MNEME-research)"}
MESES = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_REUNIAO = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
                      r"[A-Z][a-z]{2,8}/[A-Z][a-z]{2,8})\s+(\d{1,2})-(\d{1,2})\*?")
NOVA_YORK = ZoneInfo("America/New_York")


def _identidade(*partes: str) -> str:
    return hashlib.sha256("|".join(partes).encode()).hexdigest()[:16]


def fomc_da_pagina(html: str, agora: datetime | None = None) -> list[dict]:
    """Decisões do FOMC: último dia da reunião, 14h de Nova York. A data é pública com antecedência, então vale desde sempre."""
    texto = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    partes = re.split(r"(\d{4}) FOMC Meetings", texto)
    eventos = {}
    for ano, corpo in zip(partes[1::2], partes[2::2]):
        for mes, primeiro, dia in _REUNIAO.findall(corpo):
            # "Oct/Nov 30-1" termina no segundo mês; "Apr/May 28-29" ainda não virou o mês.
            nomes = mes.split("/")
            numero_mes = MESES[(nomes[-1] if int(dia) < int(primeiro) else nomes[0])[:3].lower()]
            quando = pd.Timestamp(datetime(int(ano), numero_mes, int(dia), 14, tzinfo=NOVA_YORK)).tz_convert("UTC")
            eventos[quando] = {"id": _identidade("fomc", quando.isoformat()), "ocorrido_em": quando, "recebido_em": agora, "fonte": "fed",
                               "moeda": "USD", "nome": "Decisão do FOMC", "impacto": "High", "previsao": None, "anterior": None}
    return [eventos[q] for q in sorted(eventos)]


def _texto(evento: ET.Element, campo: str) -> str | None:
    valor = (evento.findtext(campo) or "").strip()
    return valor or None


def semana_do_feed(xml: bytes | str, agora: datetime) -> list[dict]:
    """Eventos da semana, com previsão e valor anterior. Sem hora marcada (feriado, "o dia todo"), o evento não entra."""
    eventos = []
    for e in ET.fromstring(xml).iter("event"):
        data, hora = _texto(e, "date"), _texto(e, "time")
        try:
            quando = pd.to_datetime(f"{data} {hora}", format="%m-%d-%Y %I:%M%p", utc=True)
        except (ValueError, TypeError):
            continue
        nome, moeda = _texto(e, "title") or "", _texto(e, "country") or ""
        eventos.append({"id": _identidade(nome, moeda, quando.isoformat()), "ocorrido_em": quando, "recebido_em": agora, "fonte": "semana",
                        "moeda": moeda, "nome": nome, "impacto": _texto(e, "impact"), "previsao": _texto(e, "forecast"), "anterior": _texto(e, "previous")})
    return eventos


class FonteCalendario:
    def __init__(self, cliente: httpx.Client | None = None):
        self.cliente = cliente or httpx.Client(timeout=20, headers=AGENTE, follow_redirects=True)

    def fomc(self, agora: datetime | None = None) -> list[dict]:
        resposta = self.cliente.get(URL_FOMC)
        resposta.raise_for_status()
        return fomc_da_pagina(resposta.text, agora)

    def semana(self, agora: datetime) -> list[dict]:
        resposta = self.cliente.get(URL_SEMANA)
        resposta.raise_for_status()
        return semana_do_feed(resposta.content, agora)

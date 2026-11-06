"""Resultados econômicos: anterior, consenso, divulgado e surpresa, sempre pelo horário em que a informação ficou pública.

O consenso existe antes do evento, e o resultado só depois. A surpresa de um indicador é medida contra o desvio das surpresas
anteriores dele mesmo, nunca das futuras. No histórico, o "anterior" pode já estar revisado; ao vivo, cada mudança vira nova versão.
"""

from __future__ import annotations

import hashlib
import re
import time
from datetime import date, datetime, timedelta

import httpx
import numpy as np
import pandas as pd

URL = "https://api.nasdaq.com/api/calendar/economicevents"
CABECALHOS = {"user-agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36", "accept": "application/json, text/plain, */*"}

# Indicadores americanos que costumam mover o mercado. A lista é só o recorte do estudo: o impacto é medido, não suposto.
EVENTOS_CHAVE = {
    "inflacao_cpi": r"^(core )?cpi\b|consumer price", "inflacao_pce": r"\bpce\b", "inflacao_ppi": r"^(core )?ppi\b|producer price", "emprego_payroll": r"nonfarm payrolls|non-?farm", "desemprego": r"unemployment rate",
    "pedidos_desemprego": r"(initial )?jobless claims", "juros_fed": r"fed(eral)? (funds|interest)|fomc.*(rate|decision)|interest rate decision", "pib": r"\bgdp\b", "varejo": r"retail sales", "ism": r"\bism\b",
}
_MULTIPLOS = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
# O campo se chama "gmt", mas traz UTC-5 fixo, sem horário de verão. O CPI, às 8h30 de Nova York, vem 07:30 no verão e 08:30 no inverno.
DESLOCAMENTO_DA_FONTE = pd.Timedelta(hours=5)


def numero(texto: str | None) -> float | None:
    """Converte "3.1%", "65K", "-1.2B" e "$2.5" em número. Vazio ou texto vira nulo: sem dado não se inventa zero."""
    if texto is None:
        return None
    t = re.sub(r"&nbsp;|[\s$,]", "", str(texto)).rstrip("%")
    m = re.fullmatch(r"(-?\d*\.?\d+)([KMBT]?)", t, re.I)
    return float(m.group(1)) * _MULTIPLOS.get(m.group(2).upper(), 1.0) if m else None


def classe_do_evento(nome: str) -> str | None:
    baixo = nome.lower()
    return next((classe for classe, padrao in EVENTOS_CHAVE.items() if re.search(padrao, baixo)), None)


def limpo(texto) -> str:
    return re.sub(r"\s+", " ", re.sub(r"&nbsp;", " ", str(texto or ""))).strip()


def ler_dia(corpo: dict, dia: date, agora: datetime | None) -> list[dict]:
    """Uma linha por evento com hora marcada. `recebido_em` vazio indica histórico importado; ao vivo, é a hora em que chegou."""
    saida = []
    for r in ((corpo.get("data") or {}).get("rows")) or []:
        hora = str(r.get("gmt") or "").strip()
        if not re.fullmatch(r"\d{1,2}:\d{2}", hora):
            continue
        quando = pd.Timestamp(f"{dia.isoformat()} {hora}", tz="UTC") + DESLOCAMENTO_DA_FONTE
        pais, nome = limpo(r.get("country")), limpo(r.get("eventName"))
        saida.append({"id": hashlib.sha256(f"{pais}|{nome}|{quando.isoformat()}".encode()).hexdigest()[:16], "ocorrido_em": quando, "recebido_em": agora, "pais": pais, "nome": nome,
                      "classe": classe_do_evento(nome) if pais == "United States" else None, "resultado": numero(r.get("actual")), "consenso": numero(r.get("consensus")), "anterior": numero(r.get("previous"))})
    return saida


class FonteResultados:
    def __init__(self, cliente: httpx.Client | None = None, pausa: float = 1.0):
        self.cliente = cliente or httpx.Client(timeout=25, headers=CABECALHOS)
        self.pausa = pausa

    def dia(self, dia: date, agora: datetime | None) -> list[dict]:
        resposta = self.cliente.get(URL, params={"date": dia.isoformat()})
        resposta.raise_for_status()
        return ler_dia(resposta.json(), dia, agora)

    def periodo(self, inicio: date, fim: date) -> list[dict]:
        """Histórico dia a dia, com pausa entre as chamadas. Um dia que falhar fica de fora e pode ser buscado depois."""
        linhas: list[dict] = []
        d = inicio
        while d <= fim:
            try:
                linhas += self.dia(d, None)
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(self.pausa)
            d += timedelta(days=1)
        return linhas


def surpresas(eventos: pd.DataFrame, minimo_historico: int = 6) -> pd.DataFrame:
    """Surpresa = resultado - consenso, padronizada pelas surpresas anteriores do mesmo indicador. Sem histórico suficiente, fica nula."""
    # Vale o primeiro número publicado: foi a ele que o mercado reagiu. Revisões posteriores não mudam a surpresa daquele momento.
    e = eventos.dropna(subset=["resultado", "consenso", "classe"]).sort_values("recebido_em", na_position="first").drop_duplicates("id", keep="first").sort_values("ocorrido_em").copy()
    if e.empty:
        return e.assign(surpresa=[], surpresa_z=[])
    e["surpresa"] = e["resultado"] - e["consenso"]
    # Vários recortes do mesmo indicador podem sair no mesmo minuto, por isso a escala é por nome do evento.
    desvio = e.groupby("nome")["surpresa"].transform(lambda s: s.shift().expanding(minimo_historico).std())
    e["surpresa_z"] = e["surpresa"] / desvio.replace(0, np.nan)
    return e


def divulgados_e_agenda(eventos: pd.DataFrame, instante: datetime) -> pd.DataFrame:
    """Ao vivo: mantém a agenda futura, mas apaga resultados que ainda não haviam chegado naquele instante."""
    if eventos.empty:
        return eventos
    e = eventos.copy()
    limite = pd.Timestamp(instante)
    # Histórico importado não tem hora de chegada; a coluna toda vazia vem sem fuso, por isso a conversão.
    chegada = pd.to_datetime(e["recebido_em"], utc=True)
    futuro = (e["ocorrido_em"] > limite) | (chegada.notna() & (chegada > limite))
    e.loc[futuro, "resultado"] = np.nan
    return e


class ResultadosAoVivo:
    """Ontem e hoje a cada ciclo; a agenda dos próximos dias, de hora em hora. Grava só o que mudou: chegada e revisões ficam registradas."""

    def __init__(self, fonte: FonteResultados | None = None, dias_de_agenda: int = 7):
        self.fonte = fonte or FonteResultados(pausa=0)
        self.dias_de_agenda = dias_de_agenda
        self.vistos: set[tuple] = set()
        self.agenda_em: datetime | None = None

    def coletar(self, agora: datetime) -> list[dict]:
        novos = []
        hoje = agora.date()
        dias = [hoje - timedelta(days=1), hoje]
        if self.agenda_em is None or agora - self.agenda_em >= timedelta(hours=1):
            self.agenda_em = agora
            dias += [hoje + timedelta(days=i) for i in range(1, self.dias_de_agenda + 1)]
        for dia in dias:
            for linha in self.fonte.dia(dia, agora):
                chave = (linha["id"], linha["resultado"], linha["consenso"], linha["anterior"])
                if chave not in self.vistos:
                    self.vistos.add(chave)
                    novos.append(linha)
        return novos


def divulgados_ate(eventos: pd.DataFrame, instante: datetime) -> pd.DataFrame:
    """O que já era público: resultado só depois do horário do evento e, ao vivo, só depois de ter chegado."""
    limite = pd.Timestamp(instante)
    chegada = pd.to_datetime(eventos["recebido_em"], utc=True)
    chegou = chegada.isna() | (chegada <= limite)
    return eventos[(eventos["ocorrido_em"] <= limite) & chegou]

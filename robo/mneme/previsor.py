"""Previsões ao vivo, sem operar: grava antes de acontecer e confere depois. É a prova final de qualquer modelo.

    uv run python -m mneme.previsor rodar
    uv run python -m mneme.previsor placar
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from .config import PASTA_DADOS
from .dados.armazem import ArmazemVelas, agora_utc
from .dados.binance_fluxo import FonteFluxo
from .dados.calendario import FonteCalendario
from .dados.eventos import ArmazemEventos
from .dados.resultados_macro import divulgados_e_agenda
from .laboratorio.dataset import construir
from .laboratorio.estudo_eventos import com_macro
from .laboratorio.previsao import Artefato, carregar_artefato
from .laboratorio.validacao import intervalo_wilson
from .noticias import com_noticias

log = logging.getLogger("mneme.previsor")

JANELA_DIAS = 30  # o suficiente para aquecer os indicadores de 60 minutos
ATUALIZACAO = timedelta(hours=1)
IDADE_MAXIMA = timedelta(minutes=3)  # vela mais velha que isso: a coleta está parada, e prever seria enganoso
REFERENCIA = {"BTCUSDT": "ETHUSDT"}
PADRAO_REFERENCIA = "BTCUSDT"


class Previsor:
    def __init__(self, raiz: Path | str, artefatos: list[Artefato], relogio: Callable[[], datetime] = agora_utc,
                 fonte_calendario: FonteCalendario | None = None, fonte_fluxo: FonteFluxo | None = None):
        self.velas, self.eventos = ArmazemVelas(raiz), ArmazemEventos(raiz)
        self.artefatos, self.relogio = artefatos, relogio
        self.fonte_calendario, self.fonte_fluxo = fonte_calendario or FonteCalendario(), fonte_fluxo or FonteFluxo()
        self.batimento = Path(raiz) / "previsor.batimento"
        self.atualizado_em: datetime | None = None
        self.feitas: set[tuple[str, pd.Timestamp]] = set()
        for artefato in artefatos:
            anteriores = self.eventos.ler("previsoes", artefato.manifesto["par"])
            if not anteriores.empty:
                self.feitas |= {(artefato.manifesto["id"], t) for t in anteriores.loc[anteriores["modelo"] == artefato.manifesto["id"], "ocorrido_em"]}

    def atualizar_fontes(self) -> None:
        """Calendário e funding, de hora em hora. Uma fonte fora do ar não impede a previsão: os dados ficam como estão."""
        agora = self.relogio()
        if self.atualizado_em is not None and agora - self.atualizado_em < ATUALIZACAO:
            return
        self.atualizado_em = agora
        for nome, ler in (("semana", lambda: self.fonte_calendario.semana(agora)), ("fomc", lambda: self.fonte_calendario.fomc(agora))):
            try:
                self.eventos.gravar("calendario", "GLOBAL", ler())
            except (httpx.HTTPError, ValueError) as erro:
                log.warning("Calendário %s indisponível: %s", nome, erro.__class__.__name__)
        for par in {a.manifesto["par"] for a in self.artefatos}:
            try:
                self.eventos.gravar("funding", par, self.fonte_fluxo.funding_historico(par, agora - timedelta(days=3), agora))
            except (httpx.HTTPError, KeyError, ValueError) as erro:
                log.warning("Funding de %s indisponível: %s", par, erro.__class__.__name__)

    def eventos_altos(self) -> pd.Series:
        """Horários dos eventos de alto impacto em dólar. É o mesmo critério do treino: Decisão do FOMC."""
        c = self.eventos.ler("calendario", "GLOBAL")
        if c.empty:
            return pd.Series(dtype="datetime64[ms, UTC]")
        return c.loc[c["nome"] == "Decisão do FOMC", "ocorrido_em"].drop_duplicates()

    def ciclo(self) -> int:
        """Prevê para cada modelo cuja vela de grade acabou de fechar. Nunca repete, e nunca prevê com dado velho."""
        agora = self.relogio()
        self.batimento.parent.mkdir(parents=True, exist_ok=True)
        self.batimento.write_text(agora.isoformat(), encoding="utf-8")
        gravadas = 0
        cache: dict[str, pd.DataFrame] = {}
        for artefato in self.artefatos:
            m = artefato.manifesto
            par, horizonte = m["par"], m["horizonte"]
            ultima = self.velas.ultima_abertura(par)
            if ultima is None or agora - ultima - timedelta(minutes=1) > IDADE_MAXIMA:
                continue
            # Recua até a última vela de grade fechada, no máximo até onde ela ainda é recente.
            minuto = ultima.hour * 60 + ultima.minute
            vela = pd.Timestamp(ultima) - pd.Timedelta(minutes=(minuto + 1) % horizonte)
            if agora - vela.to_pydatetime() - timedelta(minutes=1) > IDADE_MAXIMA or (m["id"], vela) in self.feitas:
                continue
            if par not in cache:
                cache[par] = self._atributos(par, agora)
            if vela not in cache[par].index:
                continue
            linha = cache[par].loc[[vela]].reindex(columns=m["colunas"])
            bruta, calibrada = artefato.prever(linha)
            # A hora de chegada comprova que a previsão existia antes do resultado.
            self.eventos.gravar("previsoes", par, [{"modelo": m["id"], "horizonte": horizonte, "ocorrido_em": vela, "recebido_em": agora,
                                                    "prob_sobe_bruta": float(bruta[0]), "prob_sobe": float(calibrada[0]),
                                                    "direcao": 1 if calibrada[0] >= 0.5 else -1}])
            self.feitas.add((m["id"], vela))
            gravadas += 1
        return gravadas

    def _atributos(self, par: str, agora: datetime) -> pd.DataFrame:
        inicio = agora - timedelta(days=JANELA_DIAS)
        v = self.velas.ler(par, inicio=inicio, como_de=agora)
        referencia = self.velas.ler(REFERENCIA.get(par, PADRAO_REFERENCIA), inicio=inicio, como_de=agora)
        # O funding precisa de mais histórico que as velas: as médias do treino usam 90 pagamentos.
        funding = self.eventos.ler("funding", par, inicio=agora - timedelta(days=60), como_de=agora)
        atributos = com_macro(construir(v, funding, referencia, self.eventos_altos()), divulgados_e_agenda(self.eventos.ler("resultados_macro", "GLOBAL"), agora))
        return com_noticias(atributos, self.eventos.ler("noticias", "GLOBAL", inicio=agora - timedelta(days=8), como_de=agora), par)


def placar(raiz: Path | str, pares: list[str]) -> list[dict]:
    """Confere cada previsão com o que aconteceu: entra na abertura seguinte e sai depois do horizonte, como no backtest."""
    velas, eventos = ArmazemVelas(raiz), ArmazemEventos(raiz)
    resultado = []
    for par in pares:
        p = eventos.ler("previsoes", par)
        if p.empty:
            continue
        v = velas.ler(par, inicio=p["ocorrido_em"].min().to_pydatetime())
        for (modelo, horizonte), grupo in p.groupby(["modelo", "horizonte"]):
            certas, erradas, empates, abertas = 0, 0, 0, 0
            for linha in grupo.itertuples():
                entrada_em = linha.ocorrido_em + pd.Timedelta(minutes=1)
                saida_em = linha.ocorrido_em + pd.Timedelta(minutes=int(horizonte))
                if entrada_em not in v.index or saida_em not in v.index:
                    abertas += 1
                    continue
                variacao = (v.at[saida_em, "fechamento"] - v.at[entrada_em, "abertura"]) * linha.direcao
                certas += variacao > 0
                erradas += variacao < 0
                empates += variacao == 0
            n = certas + erradas
            resultado.append({"par": par, "modelo": modelo, "horizonte": int(horizonte), "previsoes": len(grupo), "conferidas": n, "certas": int(certas),
                              "acerto": certas / n if n else None, "limite_inferior": intervalo_wilson(int(certas), n)[0] if n else None,
                              "empates": int(empates), "abertas": abertas})
    return resultado


def carregar_todos(pasta: Path | str) -> list[Artefato]:
    """Só o modelo mais novo de cada par e horizonte. Artefato com hash errado não é usado."""
    pasta = Path(pasta)
    if not pasta.exists():
        return []
    escolhidos: dict[tuple[str, int], Artefato] = {}
    for sub in sorted(p for p in pasta.iterdir() if (p / "manifesto.json").exists()):
        try:
            a = carregar_artefato(sub)
        except ValueError as erro:
            log.error("%s", erro)
            continue
        escolhidos[(a.manifesto["par"], a.manifesto["horizonte"])] = a
    return list(escolhidos.values())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="mneme.previsor")
    parser.add_argument("comando", choices=["rodar", "placar"])
    parser.add_argument("--raiz", default=os.getenv("MNEME_DADOS_MERCADO", str(PASTA_DADOS / "mercado")))
    parser.add_argument("--modelos", default=os.getenv("MNEME_MODELOS", str(PASTA_DADOS / "modelos")))
    parser.add_argument("--pares", default=os.getenv("MNEME_PARES_VELAS", "BTCUSDT,ETHUSDT,SOLUSDT"))
    args = parser.parse_args()
    pares = [p.strip().upper() for p in args.pares.split(",") if p.strip()]
    if args.comando == "placar":
        for linha in placar(args.raiz, pares):
            print(json.dumps(linha, ensure_ascii=False))
        return
    artefatos = carregar_todos(args.modelos)
    log.info("Previsor com %d modelos; não opera, só grava e confere.", len(artefatos))
    previsor = Previsor(args.raiz, artefatos)
    parar = {"sim": False}
    for sinal in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sinal, lambda *_: parar.update(sim=True))
    while not parar["sim"]:
        try:
            previsor.atualizar_fontes()
            feitas = previsor.ciclo()
            if feitas:
                log.info("%d previsões gravadas.", feitas)
        except OSError as erro:
            log.error("Ciclo falhou: %s", erro)
        for _ in range(20):
            if parar["sim"]:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()

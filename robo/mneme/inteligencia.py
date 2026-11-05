"""Serviço de inteligência externa: notícias, calendário e, com credencial, o X.

    uv run python -m mneme.inteligencia rodar
    uv run python -m mneme.inteligencia resumo
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

from .config import PASTA_DADOS, RAIZ
from .dados.armazem import agora_utc
from .dados.calendario import FonteCalendario
from .dados.eventos import ArmazemEventos
from .dados.resultados_macro import ResultadosAoVivo
from .noticias import ATIVOS, ColetorNoticias, agrupar_eventos, medidas_de_atencao
from .social import CONSULTAS, FonteX, GastoExcedido, Limites

log = logging.getLogger("mneme.inteligencia")

MINUTOS_NOTICIAS = 5
MINUTOS_CALENDARIO = 60
MINUTOS_SOCIAL = 30
MINUTOS_RESULTADOS = 5


class Inteligencia:
    def __init__(self, raiz: Path | str, noticias: ColetorNoticias | None = None, calendario: FonteCalendario | None = None, x: FonteX | None = None, relogio=agora_utc,
                 resultados: ResultadosAoVivo | None = None):
        self.eventos = ArmazemEventos(raiz)
        self.resultados = resultados
        self.noticias, self.calendario, self.x, self.relogio = noticias or ColetorNoticias(), calendario or FonteCalendario(), x, relogio
        self.batimento = Path(raiz) / "inteligencia.batimento"
        self.ultimos: dict[str, datetime] = {}
        self.ultimo_post: dict[str, str] = {}
        # Todas as já vistas: feeds trazem itens antigos, e regravá-los falsificaria a hora em que a notícia chegou.
        self.conhecidas = set(self.eventos.ler("noticias", "GLOBAL").get("id", pd.Series(dtype=str)))

    def _na_hora(self, nome: str, minutos: int, agora: datetime) -> bool:
        if nome in self.ultimos and agora - self.ultimos[nome] < timedelta(minutes=minutos):
            return False
        self.ultimos[nome] = agora
        return True

    def ciclo(self) -> dict:
        agora = self.relogio()
        self.batimento.parent.mkdir(parents=True, exist_ok=True)
        self.batimento.write_text(agora.isoformat(), encoding="utf-8")
        resultado: dict = {}
        if self._na_hora("noticias", MINUTOS_NOTICIAS, agora):
            itens, estado = self.noticias.coletar(agora)
            # Grava só o que é novo: reler o feed não pode reescrever a hora em que a notícia chegou.
            novas = [i for i in itens if i["id"] not in self.conhecidas]
            self.eventos.gravar("noticias", "GLOBAL", novas)
            self.conhecidas |= {i["id"] for i in novas}
            resultado.update(noticias_novas=len(novas), fontes=estado)
        if self._na_hora("calendario", MINUTOS_CALENDARIO, agora):
            for nome, ler in (("semana", lambda: self.calendario.semana(agora)), ("fomc", lambda: self.calendario.fomc(agora))):
                try:
                    self.eventos.gravar("calendario", "GLOBAL", ler())
                except (httpx.HTTPError, ValueError) as erro:
                    log.warning("Calendário %s indisponível: %s", nome, erro.__class__.__name__)
        if self.resultados is not None and self._na_hora("resultados", MINUTOS_RESULTADOS, agora):
            try:
                novos = self.resultados.coletar(agora)
                self.eventos.gravar("resultados_macro", "GLOBAL", novos)
                resultado["resultados_macro_novos"] = len(novos)
            except (httpx.HTTPError, ValueError) as erro:
                log.warning("Resultados econômicos indisponíveis: %s", erro.__class__.__name__)
        if self.x is not None and self.x.ligada and self._na_hora("social", MINUTOS_SOCIAL, agora):
            resultado["posts_novos"] = self._coletar_social(agora)
        return resultado

    def _coletar_social(self, agora: datetime) -> int:
        total = 0
        for ativo, consulta in CONSULTAS.items():
            try:
                posts = self.x.buscar(consulta, agora, self.ultimo_post.get(ativo))
            except GastoExcedido as erro:
                log.warning("%s", erro)
                return total
            except httpx.HTTPError as erro:
                log.warning("X indisponível: %s", erro.__class__.__name__)
                continue
            if posts:
                self.eventos.gravar("social", "GLOBAL", posts)
                self.ultimo_post[ativo] = max((p["id"] for p in posts), key=int)
                total += len(posts)
        return total

    def atencao(self, ativo: str, indice: pd.DatetimeIndex, tipo: str = "noticias") -> pd.DataFrame:
        """Medidas para o processo central. Considera só o que já tinha chegado em cada instante."""
        return medidas_de_atencao(self.eventos.ler(tipo, "GLOBAL", inicio=indice[0].to_pydatetime() - timedelta(days=8)), ativo, indice)


def resumo(raiz: Path | str) -> None:
    eventos = ArmazemEventos(raiz)
    n = eventos.ler("noticias", "GLOBAL")
    if n.empty:
        print("Sem notícias ainda.")
        return
    n = n.sort_values("recebido_em").reset_index(drop=True)
    print(json.dumps({"noticias": len(n), "eventos": int(agrupar_eventos(n).nunique()), "por_fonte": n["fonte"].value_counts().to_dict(), "por_tipo": n["tipo"].value_counts().to_dict(),
                      "relevantes": int(n["relevante"].sum()), "suspeitas": int(n["suspeito"].sum())}, ensure_ascii=False, indent=1))
    agora = agora_utc()
    atual = pd.DatetimeIndex([pd.Timestamp(agora)])
    for ativo in ATIVOS:
        linha = medidas_de_atencao(n, ativo, atual).iloc[0].round(3).to_dict()
        print(ativo, json.dumps(linha))
    print(n.tail(6)[["fonte", "tipo", "ativos", "sentimento", "titulo"]].assign(titulo=lambda x: x["titulo"].str[:70]).to_string(index=False))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="mneme.inteligencia")
    parser.add_argument("comando", choices=["rodar", "resumo"])
    parser.add_argument("--raiz", default=os.getenv("MNEME_DADOS_MERCADO", str(PASTA_DADOS / "mercado")))
    args = parser.parse_args()
    if args.comando == "resumo":
        resumo(args.raiz)
        return
    from dotenv import load_dotenv

    load_dotenv(RAIZ / ".env")
    x = FonteX(os.getenv("X_BEARER_TOKEN", "").strip(), Limites(float(os.getenv("X_TETO_MENSAL_USD", "0") or 0)), Path(args.raiz) / "fluxo" / "x_gasto.json")
    log.info("Inteligência externa rodando. X %s.", "ligado" if x.ligada else "desligado: falta credencial e teto de gasto")
    servico = Inteligencia(args.raiz, x=x, resultados=ResultadosAoVivo())
    parar = {"sim": False}
    for sinal in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sinal, lambda *_: parar.update(sim=True))
    while not parar["sim"]:
        try:
            feito = servico.ciclo()
            if feito:
                log.info("%s", json.dumps(feito, ensure_ascii=False))
        except OSError as erro:
            log.error("Ciclo falhou: %s", erro)
        for _ in range(30):
            if parar["sim"]:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()

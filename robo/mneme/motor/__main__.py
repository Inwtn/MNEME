"""O robô multi-mercado. Só existe modo simulado: nenhuma ordem real sai daqui.

    python -m mneme.motor rodar
    python -m mneme.motor ler
    python -m mneme.motor treinar --candles 15,5
    python -m mneme.motor reproduzir --ativos XAUUSD --inicio 2026-07-01 --dias 3 --diario /tmp/d.db
    python -m mneme.motor placar
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from ..config import PASTA_DADOS
from ..dados.armazem import ArmazemVelas, agora_utc
from ..laboratorio.confluencia import SELADO_DESDE
from .ciclo import Motor
from .diario import Diario
from .modalidades import Configuracao, carregar_configuracao

log = logging.getLogger("mneme.motor")


class VelasAte:
    """Reprodução do histórico: entrega ao motor só o que já existia em cada minuto, com o mesmo código do ao vivo."""

    def __init__(self, armazem: ArmazemVelas, relogio):
        self.armazem, self.relogio, self.cache = armazem, relogio, {}

    def _todas(self, par: str) -> pd.DataFrame:
        if par not in self.cache:
            v = self.armazem.ler(par)
            self.cache[par] = v[v.index < SELADO_DESDE]  # a reprodução nunca abre a área selada
        return self.cache[par]

    def ultima_abertura(self, par: str):
        v = self._todas(par)
        v = v[v.index + pd.Timedelta(minutes=1) <= pd.Timestamp(self.relogio())]
        return v.index[-1].to_pydatetime() if len(v) else None

    def ler(self, par, inicio=None, fim=None, como_de=None):
        v = self._todas(par)
        limite = pd.Timestamp(como_de or self.relogio())
        return v[(v.index >= pd.Timestamp(inicio)) & (v.index + pd.Timedelta(minutes=1) <= limite)] if inicio is not None else v[v.index + pd.Timedelta(minutes=1) <= limite]


def reproduzir(raiz: Path, config: Configuracao, ativos: set[str], inicio: datetime, dias: int, diario: Diario, pasta_modelos: Path) -> dict:
    if inicio + timedelta(days=dias) > SELADO_DESDE.to_pydatetime():
        raise ValueError("A reprodução não pode entrar na área selada.")
    agora = {"t": inicio}
    filtrada = Configuracao(config.modo, config.banca, config.risco_por_operacao, config.min_operacoes_evidencia, config.limites, tuple(e for e in config.estrategias if e.ativo in ativos))
    motor = Motor(raiz, filtrada, diario, pasta_modelos, relogio=lambda: agora["t"], velas=VelasAte(ArmazemVelas(raiz), lambda: agora["t"]), parar_em=Path("/nao/existe"))
    motor.batimento = Path(os.devnull)
    total = {"apuradas": 0, "operadas": 0, "sombra": 0, "sem_oportunidade": 0}
    for _ in range(dias * 1440):
        agora["t"] += timedelta(minutes=1)
        for k, valor in motor.ciclo().items():
            total[k] += valor
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="mneme.motor")
    parser.add_argument("comando", choices=["rodar", "ler", "treinar", "reproduzir", "placar"])
    parser.add_argument("--raiz", default=os.getenv("MNEME_DADOS_MERCADO", str(PASTA_DADOS / "mercado")))
    parser.add_argument("--candles", default="")
    parser.add_argument("--ativos", default="")
    parser.add_argument("--inicio", default="")
    parser.add_argument("--dias", type=int, default=2)
    parser.add_argument("--diario", default="")
    args = parser.parse_args()
    raiz = Path(args.raiz)
    dados = raiz.parent
    config = carregar_configuracao(dados / "operacao.json")
    pasta_modelos = dados / "modelos" / "motor"
    diario = Diario(args.diario or dados / "operacao" / "diario.db")
    if args.comando == "placar":
        for linha in diario.placar():
            print(json.dumps(linha, ensure_ascii=False, default=float))
        return
    if args.comando == "treinar":
        from ..laboratorio.registro import Registro
        from .treino import treinar_todas

        candles = {int(c) for c in args.candles.split(",") if c} or None
        treinar_todas(config, raiz, pasta_modelos, Registro(dados / "laboratorio" / "experimentos.jsonl"), ArmazemVelas(raiz), candles)
        print("FIM", flush=True)
        return
    if args.comando == "reproduzir":
        inicio = datetime.fromisoformat(args.inicio).replace(tzinfo=timezone.utc)
        print(json.dumps(reproduzir(raiz, config, set(args.ativos.split(",")), inicio, args.dias, diario, pasta_modelos), ensure_ascii=False))
        for linha in diario.placar():
            print(json.dumps(linha, ensure_ascii=False, default=float))
        return
    parar = {"sim": False}
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, lambda *_: parar.update(sim=True))
    def dormir(segundos: float) -> None:
        for _ in range(int(segundos)):
            if parar["sim"]:
                return
            time.sleep(1)
    if args.comando == "ler":
        from ..analista import MODELO_PADRAO, ClienteLLM, URL_PADRAO
        from ..dados.eventos import ArmazemEventos
        from .leitor import servico_leitor

        log.info("Leitor de contexto rodando.")
        servico_leitor(ClienteLLM(os.getenv("MNEME_LLM_MODELO", MODELO_PADRAO), URL_PADRAO), ArmazemEventos(raiz), diario, agora_utc, lambda: parar["sim"], dormir)
        return
    log.info("Motor rodando em modo simulado." if config else "Sem operacao.json: o motor só observa.")
    motor = Motor(raiz, config, diario, pasta_modelos)
    while not parar["sim"]:
        try:
            resumo = motor.ciclo()
            if resumo["operadas"] or resumo["sombra"] or resumo["apuradas"]:
                log.info("%s", resumo)
        except OSError as erro:
            log.error("Ciclo falhou: %s", erro)
        dormir(5)


if __name__ == "__main__":
    main()

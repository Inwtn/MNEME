"""Carteira simulada ao vivo, uma por técnica. Nenhuma ordem é enviada: só grava o sinal antes do resultado e confere depois.

A hora de chegada prova que o sinal existia antes do resultado. O saldo é calculado na hora do placar, a partir dos sinais e das velas, com uma operação de cada vez,
entrada na abertura seguinte e payout suposto. Saldo em unidades de aposta: +0,85 quando ganha e -1 quando perde.

    python -m mneme.carteira rodar
    python -m mneme.carteira placar --payout 0.85
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

import numpy as np
import pandas as pd

from .config import PASTA_DADOS
from .dados.armazem import ArmazemVelas, agora_utc
from .dados.eventos import ArmazemEventos
from .laboratorio.horizontes import retorno_da_operacao, uma_por_vez
from .laboratorio.tecnicas import NOMES, todas_as_tecnicas
from .laboratorio.validacao import intervalo_wilson

log = logging.getLogger("mneme.carteira")

TEMPOS = {"5min": 5, "15min": 15}  # o tempo gráfico é também a duração da operação
DIAS_DE_JANELA = {"5min": 12, "15min": 30}
IDADE_MAXIMA = timedelta(minutes=3)
PREVISOES_ANTES_DE_CONFIAR = 100
FRACAO_CONFIANTE = 0.2
ESTRATEGIA_MODELO = "modelo: mais confiantes"


def ultima_vela_fechada(ultima_abertura: datetime, minutos: int) -> pd.Timestamp:
    """O último minuto da vela grande mais recente que já fechou por inteiro."""
    t = pd.Timestamp(ultima_abertura)
    return t - pd.Timedelta(minutes=(t.hour * 60 + t.minute + 1) % minutos)


class Carteira:
    def __init__(self, raiz: Path | str, pares: list[str], relogio: Callable[[], datetime] = agora_utc):
        self.velas, self.eventos = ArmazemVelas(raiz), ArmazemEventos(raiz)
        self.pares, self.relogio = pares, relogio
        self.batimento = Path(raiz) / "carteira.batimento"
        self.feitas: set[tuple[str, str, pd.Timestamp]] = set()
        for par in pares:
            anteriores = self.eventos.ler("carteira", par)
            if not anteriores.empty:
                self.feitas |= {(par, t, q) for t, q in zip(anteriores["tempo"], anteriores["ocorrido_em"])}

    def ciclo(self) -> int:
        """Grava os sinais das velas que acabaram de fechar. Nunca repete, e nunca decide com dado velho."""
        agora = self.relogio()
        self.batimento.parent.mkdir(parents=True, exist_ok=True)
        self.batimento.write_text(agora.isoformat(), encoding="utf-8")
        gravados = 0
        for par in self.pares:
            ultima = self.velas.ultima_abertura(par)
            if ultima is None or agora - ultima - timedelta(minutes=1) > IDADE_MAXIMA:
                continue
            for tempo, minutos in TEMPOS.items():
                vela = ultima_vela_fechada(ultima, minutos)
                if agora - vela.to_pydatetime() - timedelta(minutes=1) > IDADE_MAXIMA or (par, tempo, vela) in self.feitas:
                    continue
                v = self.velas.ler(par, inicio=agora - timedelta(days=DIAS_DE_JANELA[tempo]), como_de=agora)
                sinais = todas_as_tecnicas(v[v.index <= vela], tempo)
                linhas = []
                if vela in sinais.index:
                    linha = sinais.loc[vela]
                    linhas = [{"estrategia": NOMES.get(c, c), "tempo": tempo, "expiracao": minutos, "direcao": int(d), "ocorrido_em": vela, "recebido_em": agora} for c, d in linha.items() if d != 0]
                # Vela sem sinal também é marcada: reiniciar o serviço não pode fazê-lo decidir de novo com outra hora de chegada.
                self.eventos.gravar("carteira", par, linhas or [{"estrategia": "sem sinal", "tempo": tempo, "expiracao": minutos, "direcao": 0, "ocorrido_em": vela, "recebido_em": agora}])
                self.feitas.add((par, tempo, vela))
                gravados += len(linhas)
        return gravados


def sinais_do_modelo(previsoes: pd.DataFrame, fracao: float = FRACAO_CONFIANTE, minimo: int = PREVISOES_ANTES_DE_CONFIAR) -> pd.DataFrame:
    """As previsões gravadas, só as mais confiantes frente às anteriores do mesmo modelo. O começo fica de fora: ainda não existe passado para o corte."""
    partes = []
    for (modelo, horizonte), g in previsoes.groupby(["modelo", "horizonte"]):
        g = g.sort_values("ocorrido_em")
        confianca = (g["prob_sobe"] - 0.5).abs()
        corte = confianca.expanding(minimo).quantile(1 - fracao).shift(1)
        selecionadas = g[confianca >= corte]
        partes.append(pd.DataFrame({"estrategia": ESTRATEGIA_MODELO, "tempo": f"{int(horizonte)}min", "expiracao": int(horizonte), "direcao": selecionadas["direcao"].astype(int), "ocorrido_em": selecionadas["ocorrido_em"]}))
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=["estrategia", "tempo", "expiracao", "direcao", "ocorrido_em"])


def placar(raiz: Path | str, pares: list[str], payout: float = 0.85) -> list[dict]:
    velas, eventos = ArmazemVelas(raiz), ArmazemEventos(raiz)
    empate = 1 / (1 + payout)
    saida = []
    for par in pares:
        sinais = eventos.ler("carteira", par)
        previsoes = eventos.ler("previsoes", par)
        tabela = pd.concat([sinais[sinais["direcao"] != 0][["estrategia", "tempo", "expiracao", "direcao", "ocorrido_em"]] if not sinais.empty else pd.DataFrame(), sinais_do_modelo(previsoes) if not previsoes.empty else pd.DataFrame()], ignore_index=True)
        if tabela.empty:
            continue
        v = velas.ler(par, inicio=tabela["ocorrido_em"].min().to_pydatetime())
        for (estrategia, tempo, expiracao), g in tabela.groupby(["estrategia", "tempo", "expiracao"]):
            g = g.sort_values("ocorrido_em").drop_duplicates("ocorrido_em")
            tempos = pd.DatetimeIndex(g["ocorrido_em"])
            aceitos = uma_por_vez(tempos, 0, int(expiracao))
            t, direcao = tempos[aceitos], g["direcao"].to_numpy()[aceitos]
            r = retorno_da_operacao(v, t, 0, int(expiracao)) * direcao
            atrasado = retorno_da_operacao(v, t, 1, int(expiracao)) * direcao
            abertas = int(np.isnan(r).sum())
            validas = ~np.isnan(r) & (r != 0)
            n, certas = int(validas.sum()), int((r[validas] > 0).sum())
            validas_atraso = ~np.isnan(atrasado) & (atrasado != 0)
            saida.append({"par": par, "estrategia": estrategia, "tempo": tempo, "operacoes": n, "ganhos": certas, "perdas": n - certas, "abertas": abertas, "acerto": certas / n if n else None, "limite_inferior": intervalo_wilson(certas, n)[0] if n else None,
                          "acerto_com_atraso": float((atrasado[validas_atraso] > 0).mean()) if validas_atraso.any() else None, "saldo_unidades": certas * payout - (n - certas), "empate": empate})
    return sorted(saida, key=lambda l: -l["saldo_unidades"])


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="mneme.carteira")
    parser.add_argument("comando", choices=["rodar", "placar"])
    parser.add_argument("--raiz", default=os.getenv("MNEME_DADOS_MERCADO", str(PASTA_DADOS / "mercado")))
    parser.add_argument("--pares", default=os.getenv("MNEME_PARES_VELAS", "BTCUSDT,ETHUSDT,SOLUSDT"))
    parser.add_argument("--payout", type=float, default=0.85)
    args = parser.parse_args()
    pares = [p.strip().upper() for p in args.pares.split(",") if p.strip()]
    if args.comando == "placar":
        for linha in placar(args.raiz, pares, args.payout):
            print(json.dumps(linha, ensure_ascii=False, default=float))
        return
    log.info("Carteira simulada rodando: nenhuma ordem é enviada.")
    carteira = Carteira(args.raiz, pares)
    parar = {"sim": False}
    for sinal in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sinal, lambda *_: parar.update(sim=True))
    while not parar["sim"]:
        try:
            feitos = carteira.ciclo()
            if feitos:
                log.info("%d sinais gravados.", feitos)
        except OSError as erro:
            log.error("Ciclo falhou: %s", erro)
        for _ in range(20):
            if parar["sim"]:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()

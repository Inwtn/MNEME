"""O que vem depois de cada técnica? Cada uma é medida sozinha, com entrada na abertura seguinte, placebo e correção por múltiplos testes.

Reúne as regras das combinações e acrescenta linhas de tendência, POC, Ichimoku, MACD, Bollinger, padrões de vela, topo e fundo duplos, OCO, triângulo e VSA.
Os cortes são fixados antes de medir. Harmônicos e Elliott ficam de fora: dependem de escolhas subjetivas que ainda não foram formalizadas.

    python -m mneme.laboratorio.tecnicas
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .. import indicadores as ind
from ..config import PASTA_DADOS
from ..dados.armazem import ArmazemVelas
from ..leitura import atributos, pivos
from ..metodologias import LADOS, evidencias
from .backtest import medir_direcao, apostas_direcao
from .combinacoes import _partes, medir_regra
from .registro import Registro, impressao_dos_dados
from .validacao import empate, holm

SELADO_DESDE = pd.Timestamp("2026-08-01", tz="UTC")
TOQUE_ATR = 0.25
TOLERANCIA_OMBROS_ATR = 0.5
RECENTE = 5
PARES = ("ETHUSDT", "BTCUSDT", "SOLUSDT")
TEMPOS = ("5min", "15min", "60min")
EXPIRACOES = (5, 15, 60)
MINIMO_DE_SINAIS = 100


def ombro_cabeca_ombro(v: pd.DataFrame, a: pd.DataFrame) -> pd.Series:
    """-1: três topos, o do meio mais alto, ombros parecidos e fechamento abaixo do fundo entre eles. +1 é o inverso. Só depois de confirmar."""
    p = pivos(v, LADOS)
    atr, f = a["atr_14"].to_numpy(), v["fechamento"].to_numpy()
    topo, fundo = p["topo"].to_numpy(), p["fundo"].to_numpy()
    saida = np.zeros(len(v))
    topos: list[float] = []
    fundos: list[float] = []
    for t in range(len(v)):
        # Duas velas seguidas com o mesmo extremo são um pivô só.
        if not np.isnan(topo[t]) and not (topos and topo[t] == topos[-1]):
            topos = (topos + [topo[t]])[-3:]
        if not np.isnan(fundo[t]) and not (fundos and fundo[t] == fundos[-1]):
            fundos = (fundos + [fundo[t]])[-3:]
        if np.isnan(atr[t]):
            continue
        if len(topos) == 3 and len(fundos) >= 2 and topos[1] > max(topos[0], topos[2]) and abs(topos[0] - topos[2]) <= TOLERANCIA_OMBROS_ATR * atr[t]:
            linha = min(fundos[-2:])
            if f[t] < linha <= f[t - 1]:
                saida[t] = -1
                topos = []
        if len(fundos) == 3 and len(topos) >= 2 and fundos[1] < min(fundos[0], fundos[2]) and abs(fundos[0] - fundos[2]) <= TOLERANCIA_OMBROS_ATR * atr[t]:
            linha = max(topos[-2:])
            if f[t] > linha >= f[t - 1]:
                saida[t] = 1
                fundos = []
    return pd.Series(saida, index=v.index)


def rompimento_de_triangulo(e: pd.DataFrame) -> pd.Series:
    """LTA subindo e LTB caindo, e o fechamento atravessa uma delas: +1 pela de cima, -1 pela de baixo."""
    convergem = (e["lt_alta_inclinacao"] > 0) & (e["lt_baixa_inclinacao"] < 0)
    sobe = (e["lt_baixa_dist"] > 0) & (e["lt_baixa_dist"].shift() <= 0)
    cai = (e["lt_alta_dist"] < 0) & (e["lt_alta_dist"].shift() >= 0)
    return (sobe & convergem).astype(int) - (cai & convergem).astype(int)


def esforco_sem_resultado(v: pd.DataFrame, a: pd.DataFrame) -> pd.Series:
    """VSA: volume alto e vela estreita indicam absorção. A aposta é contra o movimento das últimas cinco velas."""
    amplitude = (v["maxima"] - v["minima"]) / a["atr_14"].replace(0, np.nan)
    absorcao = (a["volume_relativo"] >= 2.0) & (amplitude <= 0.8)
    return (-np.sign(v["fechamento"].pct_change(5, fill_method=None))).where(absorcao, 0.0).fillna(0.0)


def todas_as_tecnicas(v: pd.DataFrame, tempo: str) -> pd.DataFrame:
    """Sinal de cada técnica por vela de 1 minuto. Só vale no último minuto da vela grande, quando ela já fechou."""
    maior = ind.reamostrar(v.dropna(subset=["fechamento"]), tempo)
    a = atributos(maior)
    e = evidencias(maior, a)
    a = a.join(e)
    def lado(c, d):
        return c.fillna(False).astype(bool).astype(int) - d.fillna(False).astype(bool).astype(int)
    partes = _partes(maior, a)
    s = {nome: lado(*par) for nome, par in partes.items() if nome != "volume"}
    s["LTA: toque"] = lado(e["lt_alta_inclinacao"].gt(0) & e["lt_alta_dist"].between(0, TOQUE_ATR), pd.Series(False, index=e.index))
    s["LTB: toque"] = lado(pd.Series(False, index=e.index), e["lt_baixa_inclinacao"].lt(0) & e["lt_baixa_dist"].between(-TOQUE_ATR, 0))
    s["LTA e LTB: toque"] = s["LTA: toque"] + s["LTB: toque"]
    s["triângulo: rompimento"] = rompimento_de_triangulo(e)
    s["POC: toque"] = lado(e["vp_dist_poc"].between(0, TOQUE_ATR), e["vp_dist_poc"].between(-TOQUE_ATR, 0))
    s["Ichimoku: fora da nuvem"] = lado((e["ichi_nuvem_pos"] > 0) & (e["ichi_tk"] > 0), (e["ichi_nuvem_pos"] < 0) & (e["ichi_tk"] < 0))
    macd = a["macd_hist"]
    s["MACD: cruzamento"] = lado((macd > 0) & (macd.shift() <= 0), (macd < 0) & (macd.shift() >= 0))
    s["Bollinger: fora da banda"] = lado(a["bb_posicao"] <= 0, a["bb_posicao"] >= 1)
    s["vela: engolfo"] = lado(a["engolfo"] > 0, a["engolfo"] < 0)
    s["vela: martelo e estrela"] = lado(a["martelo"] > 0, a["estrela"] > 0)
    s["falso rompimento"] = (-a["falso_rompimento"]).astype(int).where(a["falso_rompimento"] != 0, 0)
    s["topo e fundo duplos"] = lado(e["padrao_duplo"] > 0, e["padrao_duplo"] < 0)
    s["OCO"] = ombro_cabeca_ombro(maior, a).astype(int)
    s["VSA: esforço sem resultado"] = esforco_sem_resultado(maior, a).astype(int)
    tabela = pd.DataFrame(s)
    tabela.index = tabela.index + pd.Timedelta(tempo) - pd.Timedelta(minutes=1)
    return tabela[tabela.ne(0).any(axis=1)]


NOMES = {"varredura": "varredura de liquidez", "fvg": "FVG", "fib_dourada": "Fibonacci: zona dourada", "suporte_resistencia": "suporte e resistência", "estrutura": "estrutura de mercado", "order_block": "order block",
         "spring": "Wyckoff: spring", "perfil_volume": "perfil de volume", "rsi_extremo": "RSI extremo", "divergencia": "divergência de RSI", "vwap": "VWAP", "tendencia": "tendência", "rompimento": "rompimento", "reteste": "reteste"}


def resumir(linhas: list[dict], referencia: float, minimo: int = MINIMO_DE_SINAIS) -> list[dict]:
    """Por técnica, junta os ativos, tempos e expirações. O lado contrário também aparece: técnica que erra muito também é informação, mas é hipótese nova."""
    tabela = {}
    for l in linhas:
        if l.get("sinais", 0) < minimo:
            continue
        t = tabela.setdefault(l["tecnica"], {"tecnica": l["tecnica"], "medicoes": 0, "sinais": 0, "acertos": 0, "acima_de_50": 0, "corrigidas": 0, "melhor": None})
        t["medicoes"] += 1
        t["sinais"] += l["sinais"]
        t["acertos"] += l["acertos"]
        t["acima_de_50"] += l["acerto"] > 0.5
        t["corrigidas"] += l.get("p50_ajustado", 1.0) < 0.05
        if t["melhor"] is None or l["limite_inferior"] > t["melhor"]["limite_inferior"]:
            t["melhor"] = {k: l[k] for k in ("par", "tempo", "horizonte", "sinais", "acerto", "limite_inferior")}
    return sorted(({**t, "acerto": t["acertos"] / t["sinais"]} for t in tabela.values()), key=lambda t: -t["acerto"])


def main() -> None:
    parser = argparse.ArgumentParser(prog="mneme.laboratorio.tecnicas")
    parser.add_argument("--raiz", default=os.getenv("MNEME_DADOS_MERCADO", str(PASTA_DADOS / "mercado")))
    parser.add_argument("--payout", type=float, default=0.85)
    parser.add_argument("--pasta", default=str(PASTA_DADOS / "laboratorio"))
    args = parser.parse_args()
    pasta = Path(args.pasta)
    armazem, registro = ArmazemVelas(args.raiz), Registro(pasta / "experimentos.jsonl")
    linhas = []
    for par in PARES:
        v = armazem.ler(par)
        v = v[v.index < SELADO_DESDE]
        dados = impressao_dos_dados(v)
        for tempo in TEMPOS:
            s = todas_as_tecnicas(v, tempo)
            for coluna in s.columns:
                for h in EXPIRACOES:
                    r = {"tecnica": NOMES.get(coluna, coluna), "par": par, "tempo": tempo, "horizonte": h, **medir_regra(v, s[coluna], h, args.payout)}
                    linhas.append(r)
                    registro.anotar("tecnicas", r["tecnica"], {"par": par, "tempo": tempo, "horizonte": h, "payout": args.payout}, dados, r)
            print(f"{par} {tempo}: {s.shape[1]} técnicas medidas", flush=True)
    medidas = [l for l in linhas if l.get("sinais")]
    for l, p, p50 in zip(medidas, holm([l["p_valor"] for l in medidas]), holm([l["p_contra_50"] for l in medidas])):
        l["p_ajustado"], l["p50_ajustado"] = p, p50
    resumo = resumir(medidas, empate(args.payout))
    conteudo = json.loads(json.dumps({"payout": args.payout, "empate": empate(args.payout), "medicoes": len(medidas), "resumo": resumo, "linhas": linhas}, default=float), parse_constant=lambda _: None)
    (pasta / "tecnicas.json").write_text(json.dumps(conteudo, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nEmpate {empate(args.payout):.2%}. {len(medidas)} medições. Passaram do empate após a correção: {sum(l['p_ajustado'] < 0.05 for l in medidas)}.")
    print("| Técnica | Sinais | Acerto | Medições | Acima de 50% | Corrigidas | Melhor caso |\n|---|---:|---:|---:|---:|---:|---|")
    for t in resumo:
        m = t["melhor"]
        print(f"| {t['tecnica']} | {t['sinais']} | {t['acerto']:.2%} | {t['medicoes']} | {t['acima_de_50']} | {t['corrigidas']} | {m['par'][:3]} {m['tempo']} {m['horizonte']}min {m['acerto']:.2%} n={m['sinais']} |")


if __name__ == "__main__":
    main()

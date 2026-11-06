"""Traça o que um analista traça: suportes, resistências, LTA, LTB, Fibonacci, FVG, order block, POC e VWAP. Só com o que já existia no instante.

Desenho é leitura, não previsão: o que cada técnica costuma causar é medido em `laboratorio/tecnicas.py`.

    python -m mneme.desenho ETHUSDT --tempo 15min --saida grafico.svg
"""

from __future__ import annotations

import argparse
import html
import json
import os
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from . import indicadores as ind
from .leitura import atributos, pivos
from .metodologias import LADOS, evidencias

TOLERANCIA_NIVEL_ATR = 0.5
TOLERANCIA_LINHA_ATR = 0.25
FOLGA_ROMPIMENTO_ATR = 0.5
PIVOS_POR_LINHA = 10


@dataclass
class Nivel:
    tipo: str  # suporte ou resistencia
    preco: float
    toques: int
    ultimo_toque: str


@dataclass
class Linha:
    tipo: str  # LTA ou LTB
    inicio: str
    preco_inicio: float
    fim: str
    preco_fim: float
    toques: int


@dataclass
class Desenho:
    par: str
    tempo: str
    ate: str
    preco: float
    atr: float
    niveis: list[Nivel] = field(default_factory=list)
    linhas: list[Linha] = field(default_factory=list)
    fibonacci: dict[str, float] = field(default_factory=dict)
    zonas: list[dict] = field(default_factory=list)
    referencias: dict[str, float] = field(default_factory=dict)
    padroes: list[str] = field(default_factory=list)


def _pivos_reais(v: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Topos e fundos já confirmados, na vela em que de fato ocorreram. A confirmação pede `LADOS` velas depois."""
    p = pivos(v, LADOS)
    recuar = lambda s: pd.Series(s.dropna().to_numpy(), index=v.index[np.flatnonzero(s.notna().to_numpy()) - LADOS])
    return recuar(p["topo"]), recuar(p["fundo"])


def agrupar_niveis(precos: pd.Series, atr: float, atual: float) -> list[Nivel]:
    """Pivôs a menos de meio ATR viram um nível só. Abaixo do preço é suporte, acima é resistência. Um toque só não faz nível."""
    grupos: list[list[tuple[float, pd.Timestamp]]] = []
    for preco, quando in sorted(zip(precos.to_numpy(), precos.index), key=lambda x: x[0]):
        if grupos and preco - grupos[-1][0][0] <= TOLERANCIA_NIVEL_ATR * atr:
            grupos[-1].append((preco, quando))
        else:
            grupos.append([(preco, quando)])
    niveis = []
    for g in grupos:
        if len(g) >= 2:
            medio = float(np.mean([p for p, _ in g]))
            niveis.append(Nivel("suporte" if medio < atual else "resistencia", medio, len(g), str(max(q for _, q in g))))
    return niveis


def melhor_linha(pontos: pd.Series, fechamentos: pd.Series, atr: float, sobe: bool) -> Linha | None:
    """A reta entre dois pivôs com mais toques, respeitada pelos fechamentos depois de nascer, e que chega até a vela atual."""
    if len(pontos) < 2 or not atr:
        return None
    posicao = pd.Series(np.arange(len(fechamentos)), index=fechamentos.index)
    x = posicao.reindex(pontos.index).to_numpy()
    y = pontos.to_numpy()
    c = fechamentos.to_numpy()
    sinal = 1.0 if sobe else -1.0
    melhor, melhor_nota = None, (0, -1)
    for i in range(len(x)):
        for j in range(i + 1, len(x)):
            passo = (y[j] - y[i]) / (x[j] - x[i])
            if passo * sinal <= 0:
                continue
            reta = y[i] + passo * (np.arange(int(x[i]), len(c)) - x[i])
            if ((c[int(x[i]):] - reta) * sinal < -FOLGA_ROMPIMENTO_ATR * atr).any():
                continue
            toques = int((np.abs(y[i:] - (y[i] + passo * (x[i:] - x[i]))) <= TOLERANCIA_LINHA_ATR * atr).sum())
            nota = (toques, j)
            if nota > melhor_nota:
                melhor_nota = nota
                melhor = Linha("LTA" if sobe else "LTB", str(pontos.index[i]), float(y[i]), str(fechamentos.index[-1]), float(reta[-1]), toques)
    return melhor


def desenhar(v: pd.DataFrame, par: str = "", tempo: str = "15min", janela: int = 300, maximo_niveis: int = 3) -> Desenho:
    """Recebe velas de 1 minuto e usa só as já fechadas no tempo gráfico."""
    maior = ind.reamostrar(v.dropna(subset=["fechamento"]), tempo)
    fim_da_ultima = maior.index[-1] + pd.Timedelta(tempo) - pd.Timedelta(minutes=1)
    if fim_da_ultima > v.index[-1]:
        maior = maior.iloc[:-1]  # a última vela ainda não fechou
    a = atributos(maior)
    recente, ar = maior.iloc[-janela:], a.iloc[-janela:]
    atual, atr = float(recente["fechamento"].iloc[-1]), float(ar["atr_14"].iloc[-1])
    topos, fundos = _pivos_reais(recente)
    todos = pd.concat([topos, fundos])
    niveis = agrupar_niveis(todos, atr, atual)
    abaixo = sorted((n for n in niveis if n.tipo == "suporte"), key=lambda n: atual - n.preco)[:maximo_niveis]
    acima = sorted((n for n in niveis if n.tipo == "resistencia"), key=lambda n: n.preco - atual)[:maximo_niveis]
    fechamentos = recente["fechamento"]
    lta, ltb = melhor_linha(fundos.iloc[-PIVOS_POR_LINHA:], fechamentos, atr, True), melhor_linha(topos.iloc[-PIVOS_POR_LINHA:], fechamentos, atr, False)
    d = Desenho(par, tempo, str(fechamentos.index[-1]), atual, atr, abaixo + acima, [l for l in (lta, ltb) if l])

    if len(topos) and len(fundos):
        topo, fundo = float(topos.iloc[-1]), float(fundos.iloc[-1])
        alta = fundos.index[-1] < topos.index[-1]
        perna = topo - fundo
        d.fibonacci = {str(n): round(topo - n * perna if alta else fundo + n * perna, 6) for n in (0.236, 0.382, 0.5, 0.618, 0.786)}
    e = evidencias(maior, a).iloc[-1]
    if pd.notna(e["fvg_alta_dist"]):
        d.zonas.append({"tipo": "FVG de alta", "preco": atual - float(e["fvg_alta_dist"]) * atr})
    if pd.notna(e["fvg_baixa_dist"]):
        d.zonas.append({"tipo": "FVG de baixa", "preco": atual + float(e["fvg_baixa_dist"]) * atr})
    if pd.notna(e["ob_alta_dist"]):
        d.zonas.append({"tipo": "Order block de alta", "preco": atual - float(e["ob_alta_dist"]) * atr})
    if pd.notna(e["ob_baixa_dist"]):
        d.zonas.append({"tipo": "Order block de baixa", "preco": atual + float(e["ob_baixa_dist"]) * atr})
    if pd.notna(e["vp_dist_poc"]):
        d.referencias["POC"] = atual - float(e["vp_dist_poc"]) * atr
    d.referencias["VWAP"] = float(ar["vwap"].iloc[-1])
    if lta and ltb:
        d.padroes.append("triângulo: LTA e LTB convergem")
    return d


def svg_do_desenho(v: pd.DataFrame, d: Desenho, velas: int = 140, largura: int = 1100, altura: int = 620) -> str:
    """Gráfico autônomo: velas reais com tudo o que foi traçado por cima."""
    maior = ind.reamostrar(v.dropna(subset=["fechamento"]), d.tempo)
    maior = maior[maior.index <= pd.Timestamp(d.ate)].iloc[-velas:]
    margem_e, margem_d, topo, base = 12, 190, 42, 28
    area_x, area_y = largura - margem_e - margem_d, altura - topo - base
    candidatos = [n.preco for n in d.niveis] + list(d.fibonacci.values()) + [z["preco"] for z in d.zonas] + list(d.referencias.values())
    baixo, alto = float(maior["minima"].min()), float(maior["maxima"].max())
    faixa = alto - baixo
    visiveis = [c for c in candidatos if baixo - 0.25 * faixa <= c <= alto + 0.25 * faixa]
    minimo, maximo = min([baixo] + visiveis), max([alto] + visiveis)
    y = lambda p: topo + (maximo - p) / (maximo - minimo) * area_y
    passo = area_x / len(maior)
    x = lambda i: margem_e + (i + 0.5) * passo
    partes = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura} {altura}" font-family="system-ui,sans-serif" font-size="12"><rect width="{largura}" height="{altura}" fill="#10141c"/>',
              f'<text x="{margem_e}" y="24" fill="#e6e9ef" font-size="15" font-weight="600">{html.escape(d.par)} · {html.escape(d.tempo)} · até {html.escape(d.ate[:16])} UTC · preço {d.preco:,.2f}</text>']
    rotulos = []

    def horizontal(preco, cor, texto, traco=""):
        if minimo <= preco <= maximo:
            partes.append(f'<line x1="{margem_e}" x2="{largura - margem_d}" y1="{y(preco):.1f}" y2="{y(preco):.1f}" stroke="{cor}" stroke-width="1.2" {traco} opacity="0.85"/>')
            rotulos.append((y(preco), cor, f"{texto} {preco:,.2f}"))

    for f, p in d.fibonacci.items():
        horizontal(p, "#8a7fd6", f"Fib {f}", 'stroke-dasharray="2 4"')
    for z in d.zonas:
        horizontal(z["preco"], "#d29a3a", z["tipo"], 'stroke-dasharray="6 3"')
    for nome, p in d.referencias.items():
        horizontal(p, "#4fb3c8", nome, 'stroke-dasharray="1 3"')
    for n in d.niveis:
        horizontal(n.preco, "#3fbf7f" if n.tipo == "suporte" else "#e5646a", f"{n.tipo.capitalize()} ({n.toques}x)")
    for i, (t, l) in enumerate(maior.iterrows()):
        cor = "#3fbf7f" if l["fechamento"] >= l["abertura"] else "#e5646a"
        partes.append(f'<line x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{y(l["maxima"]):.1f}" y2="{y(l["minima"]):.1f}" stroke="{cor}"/>')
        a, b = y(max(l["abertura"], l["fechamento"])), y(min(l["abertura"], l["fechamento"]))
        partes.append(f'<rect x="{x(i) - passo * 0.32:.1f}" y="{a:.1f}" width="{passo * 0.64:.1f}" height="{max(b - a, 1):.1f}" fill="{cor}"/>')
    indice = {str(t): i for i, t in enumerate(maior.index)}
    for l in d.linhas:
        ultimo = len(maior) - 1
        inicio = pd.Timestamp(l.inicio)
        i = indice.get(str(inicio))
        fim_y = l.preco_fim
        if i is None:  # a linha nasce antes da janela: corta no começo do gráfico
            minutos = pd.Timedelta(d.tempo).total_seconds() / 60
            total = (pd.Timestamp(l.fim) - inicio).total_seconds() / 60 / minutos
            ini_y = l.preco_inicio + (l.preco_fim - l.preco_inicio) * (1 - ultimo / total) if total else l.preco_inicio
            i = 0
        else:
            ini_y = l.preco_inicio
        cor = "#6fd6a0" if l.tipo == "LTA" else "#f08a8f"
        partes.append(f'<line x1="{x(i):.1f}" y1="{y(ini_y):.1f}" x2="{x(ultimo):.1f}" y2="{y(fim_y):.1f}" stroke="{cor}" stroke-width="2"/>')
        rotulos.append((y(fim_y), cor, f"{l.tipo} ({l.toques} toques) {fim_y:,.2f}"))
    rotulos.sort(key=lambda r: r[0])
    ultimo_y = -99.0
    for yy, cor, texto in rotulos:
        yy = max(yy, ultimo_y + 14)
        ultimo_y = yy
        partes.append(f'<text x="{largura - margem_d + 6}" y="{yy + 4:.1f}" fill="{cor}">{html.escape(texto)}</text>')
    partes.append("</svg>")
    return "".join(partes)


def main() -> None:
    from .config import PASTA_DADOS
    from .dados.armazem import ArmazemVelas, agora_utc

    parser = argparse.ArgumentParser(prog="mneme.desenho")
    parser.add_argument("par")
    parser.add_argument("--tempo", default="15min")
    parser.add_argument("--dias", type=int, default=20)
    parser.add_argument("--saida")
    parser.add_argument("--raiz", default=os.getenv("MNEME_DADOS_MERCADO", str(PASTA_DADOS / "mercado")))
    args = parser.parse_args()
    v = ArmazemVelas(args.raiz).ler(args.par, inicio=agora_utc() - pd.Timedelta(days=args.dias))
    d = desenhar(v, args.par, args.tempo)
    print(json.dumps(asdict(d), ensure_ascii=False, indent=1))
    if args.saida:
        with open(args.saida, "w", encoding="utf-8") as arquivo:
            arquivo.write(svg_do_desenho(v, d))


if __name__ == "__main__":
    main()

"""Leva a confluência para o gráfico do TradingView. Os pesos são treinados só com as técnicas que o Pine reproduz, para a medição valer para o que roda na tela.

    python -m mneme.motor.pine --saida pine/mneme_confluencia.pine
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

from ..config import PASTA_DADOS
from ..dados.armazem import ArmazemVelas
from ..laboratorio.confluencia import SELADO_DESDE, grade_de_sinais
from .modalidades import Estrategia, ExpiracaoFixa
from .treino import treinar_estrategia

# Na mesma ordem das variáveis do script. Cada uma tem a mesma definição de laboratorio/tecnicas.py.
TECNICAS = ("Bollinger: fora da banda", "rsi_extremo", "MACD: cruzamento", "vela: engolfo", "vela: martelo e estrela", "rompimento")
CURTOS = ("Bollinger", "RSI", "MACD", "Engolfo", "Martelo/Estrela", "Rompimento")
ATIVOS = {"XAUUSD": "ouro", "EURUSD": "forex", "GBPUSD": "forex", "USDJPY": "forex", "ETHUSDT": "cripto", "BTCUSDT": "cripto", "SOLUSDT": "cripto"}
CANDLE, EXPIRACAO, FRACAO, PAYOUT = 5, 5, 0.1, 0.85


def treinar_para_pine(armazem, ativos=ATIVOS) -> dict[str, dict]:
    modelos = {}
    for ativo, mercado in ativos.items():
        v = armazem.ler(ativo)
        v = v[v.index < SELADO_DESDE]
        sinais = grade_de_sinais(v, CANDLE)[list(TECNICAS)]
        modelos[ativo] = treinar_estrategia(Estrategia(mercado, ativo, CANDLE, EXPIRACAO, ExpiracaoFixa(PAYOUT), FRACAO), v, sinais)
        print(ativo, json.dumps({k: modelos[ativo]["evidencia"].get(k) for k in ("operacoes", "acerto", "ic95_dias")}), flush=True)
    return modelos


def _linha_do_ativo(ativo: str, m: dict) -> str:
    pesos = dict(zip(m["tecnicas"], m["pesos"]))
    numeros = ", ".join(f"{pesos[t]:.5f}" for t in TECNICAS)
    medido = m["evidencia"].get("acerto") or 0.0
    return f'    "{ativo}" => array.from({numeros}, {m["intercepto"]:.5f}, {m["corte"]:.5f}, {medido:.4f}, {m["evidencia"].get("operacoes", 0)})'


MODELO = """//@version=6
// Gerado por mneme.motor.pine. Nao edite os pesos a mao. So operacao simulada no emulador do TradingView.
strategy("MNEME | Confluencia 5 min + Linhas", overlay=true, initial_capital=10000, default_qty_type=strategy.percent_of_equity, default_qty_value=10, process_orders_on_close=false, max_lines_count=200, max_labels_count=500)

// Opera so daqui para frente: nao simula meses passados, para nao expor a area selada do laboratorio.
inicio = input.time(timestamp("__INICIO__"), "Operar a partir de")
expiracao = input.int(1, "Expiracao em velas", minval=1)
payout = input.float(__PAYOUT__, "Payout suposto", step=0.01)
soComVantagem = input.bool(false, "So operar se o medido passar do empate")

// Pesos, intercepto, corte, acerto medido e operacoes medidas, por ativo. Medidos so com dados anteriores a area selada.
dados = switch syminfo.ticker
__LINHAS__
    => array.new<float>()
conhecido = array.size(dados) > 0

[meio, topoBanda, baseBanda] = ta.bb(close, 20, 2.0)
atr = ta.atr(14)
plot(meio, "Media", color.new(color.gray, 40))
plot(topoBanda, "Banda superior", color.new(color.teal, 20))
plot(baseBanda, "Banda inferior", color.new(color.teal, 20))

lado(bool compra, bool venda) => (compra ? 1 : 0) - (venda ? 1 : 0)

rsi = ta.rsi(close, 14)
[_m, _s, hist] = ta.macd(close, 12, 26, 9)
corpo = close - open
amplitude = high - low
tamanho = math.abs(corpo)
sombraBaixo = math.min(open, close) - low
sombraCima = high - math.max(open, close)
martelo = amplitude > 0 and sombraBaixo >= 2 * tamanho and sombraBaixo / amplitude >= 0.6
estrela = amplitude > 0 and sombraCima >= 2 * tamanho and sombraCima / amplitude >= 0.6
engolfoAlta = corpo[1] < 0 and corpo > 0 and close >= open[1] and open <= close[1]
engolfoBaixa = corpo[1] > 0 and corpo < 0 and close <= open[1] and open >= close[1]

// Pivos so aparecem 3 velas depois, como na vida real. O rompimento compara com o nivel que ja existia na vela anterior.
lados = 3
topoPivo = ta.pivothigh(high, lados, lados)
fundoPivo = ta.pivotlow(low, lados, lados)
var float resistencia = na
var float suporte = na
nivelR = resistencia
nivelS = suporte
if not na(topoPivo)
    resistencia := topoPivo
if not na(fundoPivo)
    suporte := fundoPivo

sBollinger = lado(close <= baseBanda, close >= topoBanda)
sRsi = lado(rsi <= 35, rsi >= 65)
sMacd = lado(hist > 0 and hist[1] <= 0, hist < 0 and hist[1] >= 0)
sEngolfo = lado(engolfoAlta, engolfoBaixa)
sMartelo = lado(martelo, estrela)
sRompimento = lado(close > nivelR and close[1] <= nivelR, close < nivelS and close[1] >= nivelS)

nomes = array.from(__NOMES__)
var array<int> sinais = array.new<int>(6, 0)
array.set(sinais, 0, sBollinger)
array.set(sinais, 1, sRsi)
array.set(sinais, 2, sMacd)
array.set(sinais, 3, sEngolfo)
array.set(sinais, 4, sMartelo)
array.set(sinais, 5, sRompimento)

soma = 0.0
if conhecido
    soma := array.get(dados, 6)
    for i = 0 to 5
        soma += array.get(sinais, i) * array.get(dados, i)
prob = 1 / (1 + math.exp(-soma))
corte = conhecido ? array.get(dados, 7) : 1.0
medido = conhecido ? array.get(dados, 8) : 0.0
empate = 1 / (1 + payout)
confiante = math.abs(prob - 0.5) >= corte
direcao = prob >= 0.5 ? 1 : -1
liberado = conhecido and confiante and (not soComVantagem or medido > empate)

motivo(int d) =>
    aFavor = ""
    contra = ""
    for i = 0 to 5
        c = array.get(sinais, i) * array.get(dados, i) * d
        if c > 0
            aFavor += " " + array.get(nomes, i)
        else if c < 0
            contra += " " + array.get(nomes, i)
    (aFavor != "" ? "A favor:" + aFavor : "") + (contra != "" ? " | Contra:" + contra : "")

// A ordem de saida enviada no fechamento so executa na abertura seguinte: por isso o "- 1".
if strategy.position_size != 0 and bar_index - strategy.opentrades.entry_bar_index(0) >= expiracao - 1
    strategy.close_all(comment="Saida")
if strategy.position_size == 0 and barstate.isconfirmed and time >= inicio and liberado
    texto = motivo(direcao)
    strategy.entry(direcao == 1 ? "CALL" : "PUT", direcao == 1 ? strategy.long : strategy.short, comment=direcao == 1 ? "CALL" : "PUT")
    label.new(bar_index, direcao == 1 ? low : high, texto, style=direcao == 1 ? label.style_label_up : label.style_label_down, color=color.new(direcao == 1 ? color.lime : color.red, 70), textcolor=color.white, size=size.tiny)

// Linhas: LTA liga os dois ultimos fundos crescentes, LTB os dois ultimos topos decrescentes, e dois pivos proximos viram suporte ou resistencia.
var array<float> precosTopo = array.new<float>()
var array<int> barrasTopo = array.new<int>()
var array<float> precosFundo = array.new<float>()
var array<int> barrasFundo = array.new<int>()
guardar(array<float> precos, array<int> barras, float preco, int barra) =>
    array.push(precos, preco)
    array.push(barras, barra)
    if array.size(precos) > 40
        array.shift(precos)
        array.shift(barras)
if not na(topoPivo)
    guardar(precosTopo, barrasTopo, topoPivo, bar_index - lados)
if not na(fundoPivo)
    guardar(precosFundo, barrasFundo, fundoPivo, bar_index - lados)
var line lta = na
var line ltb = na
var array<line> niveis = array.new<line>()
var array<label> rotulos = array.new<label>()
desenhar(array<float> precos, array<int> barras) =>
    n = array.size(precos)
    desenhados = 0
    if n >= 2
        for i = n - 1 to 1
            for j = i - 1 to 0
                if math.abs(array.get(precos, i) - array.get(precos, j)) <= atr * 0.5 and desenhados < 3
                    nivel = (array.get(precos, i) + array.get(precos, j)) / 2
                    cor = nivel < close ? color.lime : color.red
                    array.push(niveis, line.new(array.get(barras, j), nivel, bar_index, nivel, extend=extend.right, color=color.new(cor, 30), style=line.style_dashed))
                    array.push(rotulos, label.new(bar_index + 2, nivel, nivel < close ? "Suporte" : "Resistencia", style=label.style_none, textcolor=cor, size=size.small))
                    desenhados += 1
                    break
if barstate.islast
    line.delete(lta)
    line.delete(ltb)
    while array.size(niveis) > 0
        line.delete(array.pop(niveis))
    while array.size(rotulos) > 0
        label.delete(array.pop(rotulos))
    nf = array.size(precosFundo)
    if nf >= 2
        for i = nf - 1 to 1
            if array.get(precosFundo, i) > array.get(precosFundo, i - 1)
                lta := line.new(array.get(barrasFundo, i - 1), array.get(precosFundo, i - 1), array.get(barrasFundo, i), array.get(precosFundo, i), extend=extend.right, color=color.lime, width=2)
                break
    nt = array.size(precosTopo)
    if nt >= 2
        for i = nt - 1 to 1
            if array.get(precosTopo, i) < array.get(precosTopo, i - 1)
                ltb := line.new(array.get(barrasTopo, i - 1), array.get(precosTopo, i - 1), array.get(barrasTopo, i), array.get(precosTopo, i), extend=extend.right, color=color.red, width=2)
                break
    desenhar(precosTopo, barrasTopo)
    desenhar(precosFundo, barrasFundo)

// Placar: cada operacao lida como expiracao fixa, ao lado do que foi medido antes. Poucas operacoes nao provam nada.
var int ganhos = 0
var int perdas = 0
if strategy.closedtrades > strategy.closedtrades[1]
    if strategy.closedtrades.profit(strategy.closedtrades - 1) > 0
        ganhos += 1
    else if strategy.closedtrades.profit(strategy.closedtrades - 1) < 0
        perdas += 1
var table placar = table.new(position.top_right, 2, 6, bgcolor=color.new(color.black, 20), border_width=1)
if barstate.islast
    total = ganhos + perdas
    acerto = total > 0 ? 100.0 * ganhos / total : 0.0
    saldo = ganhos * payout - perdas
    table.cell(placar, 0, 0, "Operacoes", text_color=color.white)
    table.cell(placar, 1, 0, str.tostring(total), text_color=color.white)
    table.cell(placar, 0, 1, "Acerto ao vivo", text_color=color.white)
    table.cell(placar, 1, 1, str.tostring(acerto, "#.##") + "%", text_color=acerto > 100 * empate ? color.lime : color.red)
    table.cell(placar, 0, 2, "Empate", text_color=color.white)
    table.cell(placar, 1, 2, str.tostring(100 * empate, "#.##") + "%", text_color=color.white)
    table.cell(placar, 0, 3, "Medido antes", text_color=color.white)
    table.cell(placar, 1, 3, conhecido ? str.tostring(100 * medido, "#.##") + "% em " + str.tostring(array.get(dados, 9), "#") : "ativo sem medicao", text_color=medido > empate ? color.lime : color.red)
    table.cell(placar, 0, 4, "Saldo (apostas)", text_color=color.white)
    table.cell(placar, 1, 4, str.tostring(saldo, "#.##"), text_color=saldo > 0 ? color.lime : color.red)
    table.cell(placar, 0, 5, "Simulacao sem custos", text_color=color.gray)
    table.cell(placar, 1, 5, "", text_color=color.gray)
"""


def gerar_pine(modelos: dict[str, dict], inicio: str, payout: float = PAYOUT) -> str:
    """Ativo sem modelo não opera no gráfico: o script mostra que não tem medição."""
    linhas = "\n".join(_linha_do_ativo(a, m) for a, m in modelos.items())
    nomes = ", ".join(f'"{c}"' for c in CURTOS)
    return MODELO.replace("__LINHAS__", linhas).replace("__NOMES__", nomes).replace("__INICIO__", inicio).replace("__PAYOUT__", f"{payout:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="mneme.motor.pine")
    parser.add_argument("--raiz", default=os.getenv("MNEME_DADOS_MERCADO", str(PASTA_DADOS / "mercado")))
    parser.add_argument("--saida", required=True)
    parser.add_argument("--inicio", default=None)
    args = parser.parse_args()
    inicio = args.inicio or pd.Timestamp.now(tz="UTC").floor("5min").strftime("%Y-%m-%dT%H:%M:00+00:00")
    Path(args.saida).write_text(gerar_pine(treinar_para_pine(ArmazemVelas(args.raiz)), inicio), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()

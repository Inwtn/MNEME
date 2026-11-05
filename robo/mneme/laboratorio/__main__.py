"""Refaz os estudos com o método novo, sobre as velas guardadas.

    uv run python -m mneme.laboratorio setups --minutos 5 15 --payout 0.85
    uv run python -m mneme.laboratorio spot
    uv run python -m mneme.laboratorio modelos --horizontes 5 15 --payout 0.85
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
from ..setups import SETUPS, NOME_FIMATHE, setups_configurados
from .fimathe import configuracao as configurar_fimathe, operacoes as operacoes_fimathe
from .backtest import CustoSpot, apostas_direcao, medir_direcao, medir_posicao, olha_o_futuro, operacoes_posicao, placebo_direcao
from .modelos import avaliar, preparar
from .registro import Registro, impressao_dos_dados
from .validacao import empate, holm, prob_sobreajuste, sharpe, sharpe_deflacionado


def _pct(valor: float) -> str:
    return "-" if pd.isna(valor) else f"{valor * 100:.2f}%"


def _salvar(pasta: Path, nome: str, linhas: list[dict]) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    # JSON consumido pelo painel: ausência de medição é null, nunca NaN/Infinity.
    finitos = json.loads(json.dumps(linhas, default=float), parse_constant=lambda _: None)
    (pasta / f"{nome}.json").write_text(json.dumps(finitos, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")


def estudar_setups(armazem: ArmazemVelas, registro: Registro, pares: list[str], minutos: list[int], payout: float, pasta: Path, configuracoes: dict | None = None) -> None:
    linhas, por_dia = [], {}
    familia = "setups_direcao"
    for par in pares:
        v = armazem.ler(par)
        if v.empty:
            print(f"{par}: aguardando histórico de mercado.", flush=True)
            continue
        dados = impressao_dos_dados(v)
        for nome, funcao in setups_configurados(configuracoes, par).items():
            amostra = v.iloc[-20_000:]
            vazou = olha_o_futuro(funcao, amostra)
            sinal = funcao(v)
            for m in minutos:
                apostas = apostas_direcao(v, sinal, m, payout)
                r = medir_direcao(apostas, payout)
                atraso = medir_direcao(apostas_direcao(v, sinal, m, payout, atraso_velas=1), payout)
                placebo = float(np.mean(placebo_direcao(v, sinal, m, payout, sementes=3)))
                linha = {"setup": nome, "par": par, "minutos": m, **r.como_dict(), "acerto_com_atraso_1min": atraso.acerto,
                         "placebo": placebo, "pontos_olhando_futuro": len(vazou)}
                linhas.append(linha)
                registro.anotar(familia, nome, {"par": par, "minutos": m, "payout": payout, **({"fimathe": configuracoes} if nome == NOME_FIMATHE else {})}, dados, linha)
                if len(apostas):
                    por_dia[f"{nome}|{par}|{m}"] = apostas.set_index(pd.to_datetime(apostas["quando"]))["retorno"].resample("D").sum()
                print(json.dumps({k: linha[k] for k in ("setup", "par", "minutos", "sinais", "acerto", "placebo", "pontos_olhando_futuro")}, ensure_ascii=False, default=float), flush=True)
    for linha, ajustado in zip(linhas, holm([l["p_valor"] for l in linhas])):
        linha["p_ajustado"] = ajustado
        referencia = linha["empate"]
        linha["passou"] = bool(ajustado < 0.05 and linha["acerto_primeira_metade"] > referencia and linha["acerto_segunda_metade"] > referencia
                               and linha["acerto_com_atraso_1min"] > referencia and linha["pontos_olhando_futuro"] == 0)
    if not por_dia:
        _salvar(pasta, "setups", linhas)
        print("Nenhuma amostra de sinais disponível para a comparação.")
        return
    tabela = pd.DataFrame(por_dia).fillna(0)
    pbo = prob_sobreajuste(tabela.to_numpy()) if tabela.shape[1] > 1 else float("nan")
    sharpes = tabela.apply(lambda c: sharpe(c.to_numpy()))
    melhor = sharpes.idxmax()
    dsr = sharpe_deflacionado(tabela[melhor].to_numpy(), registro.tentativas(familia), float(sharpes.var()))
    _salvar(pasta, "setups", linhas)
    print("\n| Setup | Par | Min | Sinais | Acerto | Limite inf. | Com 1 min de atraso | Placebo | p ajustado | Passou |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for l in sorted(linhas, key=lambda x: -(x["acerto"] if not pd.isna(x["acerto"]) else 0)):
        print(f"| {l['setup']} | {l['par']} | {l['minutos']} | {l['sinais']} | {_pct(l['acerto'])} | {_pct(l['limite_inferior'])} | {_pct(l['acerto_com_atraso_1min'])} | "
              f"{_pct(l['placebo'])} | {l['p_ajustado']:.3f} | {'sim' if l['passou'] else 'não'} |")
    print(f"\nEmpate com payout de {payout:.0%}: {_pct(empate(payout))}. Combinações testadas: {registro.tentativas(familia)}.")
    print(f"PBO: {pbo:.3f}. Melhor por Sharpe diário: {melhor}; Sharpe deflacionado: {dsr:.3f}.")
    print(f"Placebo médio: {_pct(float(np.mean([l['placebo'] for l in linhas])))}. Pontos olhando o futuro: {sum(l['pontos_olhando_futuro'] for l in linhas)}.")


def estudar_spot(armazem: ArmazemVelas, registro: Registro, pares: list[str], alvo: float, stop: float, velas_max: int, custo: CustoSpot, pasta: Path, configuracoes: dict | None = None) -> None:
    linhas = []
    familia = "setups_spot"
    for par in pares:
        v = armazem.ler(par)
        if v.empty:
            print(f"{par}: aguardando histórico de mercado.", flush=True)
            continue
        dados = impressao_dos_dados(v)
        atr = ind.atr(v, 14)
        for nome, funcao in setups_configurados(configuracoes, par).items():
            if nome == NOME_FIMATHE:
                regra = configurar_fimathe(configuracoes, par)
                r = medir_posicao(operacoes_fimathe(v, regra))
                parametros = {"par": par, "fimathe": configuracoes}
            else:
                r = medir_posicao(operacoes_posicao(v, funcao(v), atr, alvo, stop, velas_max, custo))
                parametros = {"par": par, "alvo_atr": alvo, "stop_atr": stop, "velas_max": velas_max, "taxa": custo.taxa, "slippage": custo.slippage}
            linha = {"setup": nome, "par": par, "execucao": "risco_configurado" if nome == NOME_FIMATHE else "spot_atr", **r.como_dict()}
            linhas.append(linha)
            registro.anotar(familia, nome, parametros, dados, linha)
            print(json.dumps({k: linha[k] for k in ("setup", "par", "operacoes", "retorno_medio_pct")}, ensure_ascii=False, default=float), flush=True)
    for linha, ajustado in zip(linhas, holm([l["p_valor"] for l in linhas])):
        linha["p_ajustado"] = ajustado
    _salvar(pasta, "spot", linhas)
    print(f"\nSó compra, alvo {alvo} ATR, stop {stop} ATR, até {velas_max} min, taxa {custo.taxa:.2%} e slippage {custo.slippage:.2%} por ponta.")
    if configurar_fimathe(configuracoes):
        print("Fimathe usa lote, custos e stop/alvo da configuração, nos dois lados; retorno sobre o patrimônio, sem substituir a regra por ATR.")
    print("| Setup | Par | Operações | Acerto | Retorno médio | Total | Pior queda | p ajustado |\n|---|---|---:|---:|---:|---:|---:|---:|")
    for l in sorted(linhas, key=lambda x: -(x["retorno_medio_pct"] if not pd.isna(x["retorno_medio_pct"]) else -99)):
        print(f"| {l['setup']} | {l['par']} | {l['operacoes']} | {_pct(l['acerto'])} | {l['retorno_medio_pct']:.3f}% | {l['retorno_total_pct']:.1f}% | {l['pior_queda_pct']:.1f}% | {l['p_ajustado']:.3f} |")


def estudar_modelos(armazem: ArmazemVelas, registro: Registro, pares: list[str], horizontes: list[int], payout: float, pasta: Path) -> None:
    referencia = empate(payout)
    linhas = []
    for par in pares:
        v = armazem.ler(par)
        if v.empty:
            print(f"{par}: aguardando histórico de mercado.", flush=True)
            continue
        dados = impressao_dos_dados(v)
        for h in horizontes:
            x, y = preparar(v, h)
            for r in avaliar(x, y, referencia):
                linha = {"par": par, "horizonte": h, **r.como_dict()}
                linhas.append(linha)
                registro.anotar("modelos_velas", r.modelo, {"par": par, "horizonte": h, "payout": payout}, dados, linha)
                print(json.dumps(linha, ensure_ascii=False, default=float), flush=True)
    for linha, ajustado in zip(linhas, holm([l["p_valor"] for l in linhas])):
        linha["p_ajustado"] = ajustado
    _salvar(pasta, "modelos", linhas)
    print(f"\nEmpate: {_pct(referencia)}.\n| Modelo | Par | Min | Previsões | Acerto | 20% mais confiantes | Rótulo embaralhado | p ajustado |\n|---|---|---:|---:|---:|---:|---:|---:|")
    for l in linhas:
        print(f"| {l['modelo']} | {l['par']} | {l['horizonte']} | {l['previsoes']} | {_pct(l['acerto'])} | {_pct(l['acerto_confiante'])} | {_pct(l['acerto_rotulo_embaralhado'])} | {l['p_ajustado']:.3f} |")


def main() -> None:
    parser = argparse.ArgumentParser(prog="mneme.laboratorio")
    parser.add_argument("--pares", default=os.getenv("MNEME_PARES_VELAS", "BTCUSDT,ETHUSDT,SOLUSDT"))
    parser.add_argument("--raiz", default=os.getenv("MNEME_DADOS_MERCADO", str(PASTA_DADOS / "mercado")))
    parser.add_argument("--saida", default=str(PASTA_DADOS / "laboratorio"))
    parser.add_argument("--config-estrategias", type=Path, help="JSON exportado por Configurações; sem regra completa, Fimathe só observa")
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("catalogo", help="Lista o mesmo catálogo de setups e modelos, incluindo Fimathe")
    f = sub.add_parser("fimathe", help="Avalia CSV de XAUUSD no registro comum de experimentos")
    f.add_argument("--config", type=Path, required=True)
    f.add_argument("--csv", type=Path, required=True)
    f.add_argument("--fonte", required=True)
    s = sub.add_parser("setups")
    s.add_argument("--minutos", type=int, nargs="+", default=[5, 15])
    s.add_argument("--payout", type=float, default=0.85)
    p = sub.add_parser("spot")
    p.add_argument("--alvo", type=float, default=2.0)
    p.add_argument("--stop", type=float, default=2.0)
    p.add_argument("--velas", type=int, default=60)
    p.add_argument("--taxa", type=float, default=0.001)
    p.add_argument("--slippage", type=float, default=0.0002)
    m = sub.add_parser("modelos")
    m.add_argument("--horizontes", type=int, nargs="+", default=[5, 15])
    m.add_argument("--payout", type=float, default=0.85)
    args = parser.parse_args()
    pares = [x.strip().upper() for x in args.pares.split(",") if x.strip()]
    pasta = Path(args.saida)
    registro = Registro(pasta / "experimentos.jsonl")
    configuracoes = json.loads(args.config_estrategias.read_text(encoding="utf-8-sig")) if args.config_estrategias else None
    if args.comando == "catalogo":
        from .catalogo import catalogo
        print(json.dumps(catalogo(), ensure_ascii=False, indent=2))
        return
    if args.comando == "fimathe":
        from ..fimathe import executar
        from .fimathe import NOME
        cfg = json.loads(args.config.read_text(encoding="utf-8-sig"))
        resultado = executar(cfg, args.csv.read_text(encoding="utf-8-sig"), args.fonte)
        if resultado["status"] != "observacao":
            registro.anotar("setups_posicao", NOME, cfg, resultado["source"]["sha256"], resultado["metrics"])
        _salvar(pasta, "fimathe", [resultado])
        print(json.dumps(resultado.get("metrics", resultado), ensure_ascii=False, indent=2))
        return
    armazem = ArmazemVelas(args.raiz)
    if args.comando == "setups":
        estudar_setups(armazem, registro, pares, args.minutos, args.payout, pasta, configuracoes)
    elif args.comando == "spot":
        estudar_spot(armazem, registro, pares, args.alvo, args.stop, args.velas, CustoSpot(args.taxa, args.slippage), pasta, configuracoes)
    else:
        estudar_modelos(armazem, registro, pares, args.horizontes, args.payout, pasta)


if __name__ == "__main__":
    main()

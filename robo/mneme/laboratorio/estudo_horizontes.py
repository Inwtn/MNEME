"""Roda a comparação de horizontes por fases, cada uma retomável, em dados só até o início da área selada.

    python -m mneme.laboratorio.estudo_horizontes custos
    python -m mneme.laboratorio.estudo_horizontes previsoes
    python -m mneme.laboratorio.estudo_horizontes regras
    python -m mneme.laboratorio.estudo_horizontes volatilidade
    python -m mneme.laboratorio.estudo_horizontes atributos
    python -m mneme.laboratorio.estudo_horizontes multi
    python -m mneme.laboratorio.estudo_horizontes relatorio
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

from ..config import PASTA_DADOS
from ..dados.armazem import ArmazemVelas
from ..dados.eventos import ArmazemEventos
from .dataset import alvos, construir, contexto_maior
from .estudo_eventos import COLUNAS_AGENDA, com_macro
from .horizontes import (BASE_DE_RETORNOS, EXPIRACOES, GRUPOS_DE_ATRIBUTOS, HORIZONTES, Cenario, alvo_de_amplitude, amostrar_grade, avaliar_previsoes, comparar_atributos, custos_do_livro, desequilibrio_do_livro,
                        medir_regra_de_movimento, por_condicao, prever_cenario, medir_multi_tempo)
from .previsao import CLASSIFICADORES, prever_regressao
from .registro import Registro, impressao_dos_dados

SELADO_DESDE = pd.Timestamp("2026-08-01", tz="UTC")
REFERENCIA = {"BTCUSDT": "ETHUSDT"}
PADRAO_REFERENCIA = "BTCUSDT"
PARES = ("ETHUSDT", "BTCUSDT", "SOLUSDT")
CENARIOS_PRINCIPAIS = tuple(Cenario(h, h) for h in (5, 1, 15, 30, 60))
CENARIOS_CRUZADOS = (Cenario(1, 5), Cenario(5, 15), Cenario(5, 60), Cenario(15, 60))
PRIORIDADE = (1, 5)


def so_desenvolvimento(tabela: pd.DataFrame, corte: pd.Timestamp = SELADO_DESDE) -> pd.DataFrame:
    """A área selada é retirada antes de qualquer cálculo. A saída de uma operação perto do corte vira vazio, em vez de olhar além dele."""
    return tabela[tabela.index < corte]


def _dados(armazem: ArmazemVelas, raiz: str, par: str, contexto: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    v = so_desenvolvimento(armazem.ler(par))
    referencia = so_desenvolvimento(armazem.ler(REFERENCIA.get(par, PADRAO_REFERENCIA)))
    eventos = ArmazemEventos(raiz)
    calendario = eventos.ler("calendario", "GLOBAL", fim=SELADO_DESDE)
    fomc = calendario.loc[calendario["nome"] == "Decisão do FOMC", "ocorrido_em"].drop_duplicates() if not calendario.empty else pd.Series(dtype="datetime64[ms, UTC]")
    x = com_macro(construir(v, eventos.ler("funding", par, fim=SELADO_DESDE), referencia, fomc), eventos.ler("resultados_macro", "GLOBAL", fim=SELADO_DESDE))
    if contexto:
        x = x.join(contexto_maior(v))
    return x, v, impressao_dos_dados(v)


def _caminho(pasta: Path, nome: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta / nome


def _guardar(pasta: Path, nome: str, conteudo) -> None:
    limpo = json.loads(json.dumps(conteudo, default=float), parse_constant=lambda _: None)
    _caminho(pasta, f"{nome}.json").write_text(json.dumps(limpo, ensure_ascii=False, indent=1), encoding="utf-8")


def _ler(pasta: Path, nome: str, padrao):
    arquivo = pasta / f"{nome}.json"
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else padrao


def fase_custos(raiz: str, pasta: Path) -> dict:
    eventos = ArmazemEventos(raiz)
    custos = {par: custos_do_livro(eventos.ler("livro", par)) for par in PARES}
    _guardar(pasta, "custos", custos)
    print(json.dumps(custos, ensure_ascii=False), flush=True)
    return custos


def fase_previsoes(armazem: ArmazemVelas, raiz: str, pasta: Path, registro: Registro, cenarios: tuple[Cenario, ...]) -> None:
    """Treina cada cenário uma vez e guarda as previsões: testar outra entrada ou expiração não exige novo treino."""
    custos = _ler(pasta, "custos", {})
    for par in PARES:
        base, v, dados = _dados(armazem, raiz, par)
        base = base[[c for c in base if c not in COLUNAS_AGENDA]]
        for c in cenarios:
            arquivo = _caminho(pasta, f"prev_{par}_c{c.candle}_h{c.horizonte}.parquet")
            if arquivo.exists():
                continue
            x, y = amostrar_grade(base, alvos(v, c.horizonte), c.candle)
            prever_cenario(x, y["sobe"], c, CLASSIFICADORES["LightGBM"]).to_parquet(arquivo, compression="zstd")
            registro.anotar("horizontes_previsao", "LightGBM", {"par": par, "candle": c.candle, "horizonte": c.horizonte}, dados, {"linhas": len(x)})
            print(f"{par} candle {c.candle} previsão {c.horizonte}: {len(x)} linhas", flush=True)
        del base


def fase_regras(armazem: ArmazemVelas, pasta: Path, registro: Registro) -> None:
    custos = _ler(pasta, "custos", {})
    linhas = []
    for par in PARES:
        v = so_desenvolvimento(armazem.ler(par))
        for olhar in HORIZONTES:
            for expiracao in EXPIRACOES:
                for atraso in (0, 1):
                    r = medir_regra_de_movimento(v, olhar, expiracao, atraso, custos.get(par))
                    for nome, m in r.items():
                        linhas.append({"par": par, "olhar": olhar, "expiracao": expiracao, "atraso": atraso, "estrategia": nome, **m})
            print(f"{par} regra {olhar} min pronta", flush=True)
    _guardar(pasta, "regras", linhas)
    registro.anotar("horizontes_regras", "movimento", {"pares": list(PARES)}, "", {"medicoes": len(linhas)})


def fase_volatilidade(armazem: ArmazemVelas, raiz: str, pasta: Path, registro: Registro) -> None:
    linhas = []
    for par in PARES:
        base, v, dados = _dados(armazem, raiz, par)
        base = base[[c for c in base if c not in COLUNAS_AGENDA]]
        for h in HORIZONTES:
            candle = max(h, 5)  # no alvo de 1 minuto, uma amostra a cada 5 já cobre 24 meses
            alvo, referencia = alvo_de_amplitude(v, h)
            x, y = amostrar_grade(base, alvos(v, h), candle)
            r = {"par": par, "horizonte": h, **prever_regressao(x, alvo.reindex(x.index), referencia.reindex(x.index))}
            linhas.append(r)
            registro.anotar("horizontes_volatilidade", "LightGBM", {"par": par, "horizonte": h}, dados, r)
            print(json.dumps(r, default=float), flush=True)
        del base
    _guardar(pasta, "volatilidade", linhas)


def fase_atributos(armazem: ArmazemVelas, raiz: str, pasta: Path, registro: Registro) -> None:
    """Cada grupo sozinho sobre os retornos, e o que se perde tirando ele de tudo. Prioridade em 1 e 5 minutos."""
    linhas = _ler(pasta, "atributos", [])
    feitos = {(l["par"], l["horizonte"], l["grupo"], l["teste"]) for l in linhas}
    for par in PARES:
        base, v, dados = _dados(armazem, raiz, par, contexto=True)
        base = base.astype({c: "float32" for c in base.columns if base[c].dtype == "float64"})
        for h in (*PRIORIDADE, 15):
            candle = 5 if h == 1 else h  # 1 minuto com uma amostra a cada 5: treinar 12 grupos em 1 milhão de linhas não cabe
            c = Cenario(candle, h)
            x, y = amostrar_grade(base, alvos(v, h), candle)
            todas = list(x.columns)
            retornos = [k for k in todas if k.startswith(BASE_DE_RETORNOS)]
            for grupo, pertence in GRUPOS_DE_ATRIBUTOS.items():
                colunas = [k for k in todas if pertence(k)]
                for teste, a, b in (("sozinho", retornos, retornos + [k for k in colunas if k not in retornos]), ("incremental", [k for k in todas if k not in colunas], todas)):
                    if (par, h, grupo, teste) in feitos:
                        continue
                    r = {"par": par, "horizonte": h, "grupo": grupo, "teste": teste, "colunas": len(colunas), **comparar_atributos(x, y["sobe"], c, a, b)}
                    linhas.append(r)
                    registro.anotar("horizontes_atributos", grupo, {"par": par, "horizonte": h, "teste": teste}, dados, r)
                    _guardar(pasta, "atributos", linhas)
                    print(json.dumps({k: r.get(k) for k in ("par", "horizonte", "grupo", "teste", "ganho_auc", "ic95", "demonstrado")}, ensure_ascii=False, default=float), flush=True)
            del x, y
        del base


def fase_multi(armazem: ArmazemVelas, raiz: str, pasta: Path, registro: Registro) -> None:
    """A hipótese de 1h, 15, 5 e 1 min por regras, e por modelo somando um tempo gráfico de cada vez."""
    custos = _ler(pasta, "custos", {})
    regras, modelos = [], []
    for par in PARES:
        base, v, dados = _dados(armazem, raiz, par, contexto=True)
        for expiracao in (5, 15, 60):
            regras += [{"par": par, **l} for l in medir_multi_tempo(base, v, expiracao, custos.get(par))]
        _guardar(pasta, "multi_regras", regras)
        print(f"{par}: regras multi-tempo prontas", flush=True)
        base = base.astype({c: "float32" for c in base.columns if base[c].dtype == "float64"})
        for h in PRIORIDADE:
            candle = 5
            x, y = amostrar_grade(base, alvos(v, h), candle)
            todas = list(x.columns)
            so_1 = [k for k in todas if k.startswith(("v_retorno", "v_volatilidade", "f_"))]
            degraus = {"+ 5 min": [k for k in todas if k.startswith("v_5min")], "+ 15 min": [k for k in todas if k.startswith(("v_15min", "m_15min"))], "+ 60 min": [k for k in todas if k.startswith(("v_60min", "m_60min"))], "+ 4h e diário": [k for k in todas if k.startswith("x_")]}
            atual = so_1
            for nome, extra in degraus.items():
                proximo = atual + extra
                r = {"par": par, "horizonte": h, "degrau": nome, **comparar_atributos(x, y["sobe"], Cenario(candle, h), atual, proximo)}
                modelos.append(r)
                registro.anotar("horizontes_multi", nome, {"par": par, "horizonte": h}, dados, r)
                print(json.dumps({k: r.get(k) for k in ("par", "horizonte", "degrau", "auc_sem", "auc_com", "ganho_auc", "demonstrado")}, ensure_ascii=False, default=float), flush=True)
                atual = proximo
            _guardar(pasta, "multi_modelos", modelos)
        del base


def fase_relatorio(armazem: ArmazemVelas, raiz: str, pasta: Path, registro: Registro) -> None:
    custos = _ler(pasta, "custos", {})
    saida = []
    condicoes = []
    eventos = ArmazemEventos(raiz)
    for par in PARES:
        v_todas = armazem.ler(par)
        v = so_desenvolvimento(v_todas)
        for arquivo in sorted(pasta.glob(f"prev_{par}_c*.parquet")):
            nome = arquivo.stem.split("_")
            candle, horizonte = int(nome[2][1:]), int(nome[3][1:])
            p = pd.read_parquet(arquivo)
            r = avaliar_previsoes(p, v, custos.get(par))
            saida.append({"par": par, "candle": candle, "horizonte": horizonte, **r})
            condicoes.append({"par": par, "candle": candle, "horizonte": horizonte, **por_condicao(p, v, horizonte)})
            print(f"{par} candle {candle} previsão {horizonte} avaliado", flush=True)
        # Prévia do livro usa só o que foi coletado agora, período que nenhum modelo treinou.
        livro = eventos.ler("livro", par)
        _guardar(pasta, f"livro_{par}", desequilibrio_do_livro(livro, v_todas))
    _guardar(pasta, "matriz", saida)
    _guardar(pasta, "condicoes", condicoes)
    registro.anotar("horizontes_matriz", "LightGBM", {"pares": list(PARES)}, "", {"cenarios": len(saida)})


def main() -> None:
    parser = argparse.ArgumentParser(prog="mneme.laboratorio.estudo_horizontes")
    parser.add_argument("fase", choices=["custos", "previsoes", "cruzados", "regras", "volatilidade", "atributos", "multi", "relatorio"])
    parser.add_argument("--raiz", default=os.getenv("MNEME_DADOS_MERCADO", str(PASTA_DADOS / "mercado")))
    parser.add_argument("--pasta", default=str(PASTA_DADOS / "laboratorio" / "horizontes"))
    args = parser.parse_args()
    armazem, pasta = ArmazemVelas(args.raiz), Path(args.pasta)
    registro = Registro(Path(args.pasta).parent / "experimentos.jsonl")
    if args.fase == "custos":
        fase_custos(args.raiz, pasta)
    elif args.fase == "previsoes":
        fase_previsoes(armazem, args.raiz, pasta, registro, CENARIOS_PRINCIPAIS)
    elif args.fase == "cruzados":
        fase_previsoes(armazem, args.raiz, pasta, registro, CENARIOS_CRUZADOS)
    elif args.fase == "regras":
        fase_regras(armazem, pasta, registro)
    elif args.fase == "volatilidade":
        fase_volatilidade(armazem, args.raiz, pasta, registro)
    elif args.fase == "atributos":
        fase_atributos(armazem, args.raiz, pasta, registro)
    elif args.fase == "multi":
        fase_multi(armazem, args.raiz, pasta, registro)
    else:
        fase_relatorio(armazem, args.raiz, pasta, registro)


if __name__ == "__main__":
    main()

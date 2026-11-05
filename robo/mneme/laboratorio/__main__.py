"""Refaz os estudos com o método novo, sobre as velas guardadas.

    uv run python -m mneme.laboratorio setups --minutos 5 15 --payout 0.85
    uv run python -m mneme.laboratorio spot
    uv run python -m mneme.laboratorio modelos --horizontes 5 15 --payout 0.85
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .. import indicadores as ind
from ..config import PASTA_DADOS
from ..dados.armazem import ArmazemVelas, agora_utc
from ..dados.calendario import FonteCalendario
from ..dados.eventos import ArmazemEventos
from ..dados.resultados_macro import FonteResultados, surpresas
from ..noticias import com_noticias
from .combinacoes import COMBINACOES, medir_regra, sinais, sobreposicao
from .estudo_eventos import com_macro, ganho_da_agenda, reacoes, resumir, volatilidade_em_torno
from ..previsor import PADRAO_REFERENCIA, REFERENCIA
from ..setups import SETUPS, NOME_FIMATHE, setups_configurados
from .avaliacao import separar_selado
from .fimathe import configuracao as configurar_fimathe, operacoes as operacoes_fimathe
from .backtest import CustoSpot, apostas_direcao, medir_direcao, medir_posicao, olha_o_futuro, operacoes_posicao, placebo_direcao
from .dataset import FAMILIAS, alvos, amostrar, colunas_de, construir
from .modelos import avaliar, preparar
from .previsao import CLASSIFICADORES, avaliar_selado, meta_rotulo, prever_direcao, prever_regressao, treinar_artefato
from .registro import Registro, commit_atual, impressao_dos_dados
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


# Daqui em diante é a área selada: nenhuma escolha de atributo, modelo ou corte pode olhar para ela.
SELADO_DESDE = pd.Timestamp("2026-08-01", tz="UTC")
CONJUNTOS = {"só preço": ("v_",), "preço + metodologias": ("v_", "m_"), "preço + agressão": ("v_", "f_"), "preço + outro mercado": ("v_", "c_"),
             "preço + derivativos": ("v_", "d_"), "preço + relógio e eventos": ("v_", "t_", "e_"), "tudo": FAMILIAS}


def _base_de_previsao(armazem: ArmazemVelas, par: str, raiz: str) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    v = armazem.ler(par)
    referencia = armazem.ler(REFERENCIA.get(par, PADRAO_REFERENCIA))
    eventos = ArmazemEventos(raiz)
    atributos = com_macro(construir(v, eventos.ler("funding", par), referencia, _fomc(raiz)), eventos.ler("resultados_macro", "GLOBAL"))
    return com_noticias(atributos, eventos.ler("noticias", "GLOBAL"), par), v, impressao_dos_dados(v)


def _fomc(raiz: str) -> pd.Series:
    eventos = ArmazemEventos(raiz)
    if eventos.ler("calendario", "GLOBAL").empty:
        eventos.gravar("calendario", "GLOBAL", FonteCalendario().fomc())
    c = eventos.ler("calendario", "GLOBAL")
    return c.loc[c["nome"] == "Decisão do FOMC", "ocorrido_em"].drop_duplicates()


def estudar_previsao(armazem: ArmazemVelas, registro: Registro, raiz: str, pares: list[str], horizontes: list[int], payout: float, pasta: Path) -> None:
    alvo_empate = empate(payout)
    direcao, familias, regressao = [], [], []
    for par in pares:
        atributos, v, dados = _base_de_previsao(armazem, par, raiz)
        print(f"{par}: {atributos.shape[1]} atributos", flush=True)
        for h in horizontes:
            x, y = amostrar(atributos, alvos(v, h), h)
            dev, _ = separar_selado(x.index, SELADO_DESDE)
            x, y = x[dev], y[dev]
            for r in prever_direcao(x, y["sobe"], alvo_empate):
                linha = {"par": par, "horizonte": h, **r.como_dict()}
                direcao.append(linha)
                registro.anotar("previsao_direcao", r.modelo, {"par": par, "horizonte": h, "conjunto": "tudo"}, dados, linha)
            print(json.dumps(direcao[-1], ensure_ascii=False, default=float), flush=True)
            for nome, prefixos in CONJUNTOS.items():
                if nome == "tudo":
                    continue
                r = prever_direcao(x[colunas_de(x, prefixos)], y["sobe"], alvo_empate, {"LightGBM": CLASSIFICADORES["LightGBM"]})[0]
                linha = {"par": par, "horizonte": h, "conjunto": nome, **r.como_dict()}
                familias.append(linha)
                registro.anotar("previsao_familias", "LightGBM", {"par": par, "horizonte": h, "conjunto": nome}, dados, linha)
            for alvo, base in (("vol_futura", np.log(x["v_volatilidade_60"].replace(0, np.nan))), ("eficiencia", x["v_60min_adx"])):
                r = prever_regressao(x, y[alvo], base)
                regressao.append({"par": par, "horizonte": h, "alvo": alvo, **r})
                registro.anotar("previsao_regressao", alvo, {"par": par, "horizonte": h}, dados, regressao[-1])
    for linha, ajustado in zip(direcao, holm([l["p_valor"] for l in direcao])):
        linha["p_ajustado"] = ajustado
    _salvar(pasta, "previsao_direcao", direcao)
    _salvar(pasta, "previsao_familias", familias)
    _salvar(pasta, "previsao_regressao", regressao)
    print(f"\nEmpate: {_pct(alvo_empate)}. Desenvolvimento até {SELADO_DESDE.date()}; corte dos confiantes só com o passado.")
    print("| Modelo | Par | Min | Previsões | Acerto | AUC | Confiantes | Brier | Brier calibrado | Erro calibração | Expectativa | p ajustado |\n|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for l in direcao:
        print(f"| {l['modelo']} | {l['par']} | {l['horizonte']} | {l['previsoes']} | {_pct(l['acerto'])} | {l['auc']:.4f} | {_pct(l['acerto_confiante'])} | {l['brier']:.4f} | {l['brier_calibrado']:.4f} | "
              f"{l['erro_calibracao_calibrado']:.4f} | {l['metricas_confiantes']['expectativa']:.4f} | {l['p_ajustado']:.3f} |")
    tabela = pd.DataFrame(familias)
    resumo = tabela.groupby(["conjunto", "horizonte"])[["acerto", "auc", "acerto_confiante"]].mean().reset_index()
    print("\nMédia entre os pares, com LightGBM:\n| Dados usados | Min | Acerto | AUC | 20% mais confiantes |\n|---|---:|---:|---:|---:|")
    for l in resumo.itertuples():
        print(f"| {l.conjunto} | {l.horizonte} | {_pct(l.acerto)} | {l.auc:.4f} | {_pct(l.acerto_confiante)} |")
    print("\nVolatilidade e eficiência contra a referência:\n| Par | Min | Alvo | R² modelo | R² referência | Ganho |\n|---|---:|---|---:|---:|---:|")
    for l in regressao:
        print(f"| {l['par']} | {l['horizonte']} | {l['alvo']} | {l['r2_modelo']:.3f} | {l['r2_referencia']:.3f} | {l['ganho_sobre_referencia']:.3f} |")


def estudar_meta(armazem: ArmazemVelas, registro: Registro, raiz: str, pares: list[str], minutos: int, payout: float, pasta: Path) -> None:
    """Meta-rótulo: o modelo aprende, com todas as evidências, quando confiar em cada regra de reversão."""
    referencia = empate(payout)
    linhas = []
    familia = "meta_rotulo_corte_passado"
    for par in pares:
        atributos, v, dados = _base_de_previsao(armazem, par, raiz)
        for nome in ("Bollinger + RSI (volta para a banda)", "Reversão após movimento forte de 1 h"):
            apostas = apostas_direcao(v, SETUPS[nome](v), minutos, payout).set_index("quando")
            x = atributos.reindex(apostas.index).copy()
            x["regra_direcao"] = apostas["direcao"]
            dev, _ = separar_selado(x.index, SELADO_DESDE)
            r = {"par": par, "setup": nome, "ate": str(SELADO_DESDE.date()), **meta_rotulo(x[dev], apostas["ganhou"][dev], referencia)}
            linhas.append(r)
            registro.anotar(familia, nome, {"par": par, "minutos": minutos, "payout": payout}, dados, r)
    tentativas = registro.tentativas(familia) + registro.tentativas("meta_rotulo")
    for linha, ajustado in zip(linhas, holm([l["p_valor"] for l in linhas])):
        linha["p_ajustado"] = ajustado
        linha["p_por_tentativas"] = min(1.0, linha["p_valor"] * tentativas)
    _salvar(pasta, "meta", linhas)
    print(f"\nEmpate: {_pct(referencia)}. {minutos} min. Desenvolvimento até {SELADO_DESDE.date()}. Corte só com o passado. Tentativas nessa pergunta: {tentativas}.")
    print("| Regra | Par | Sinais | Acerto todos | Selecionados | Acerto selecionados | Lim. inf. | AUC | Expectativa | Fator lucro | Pior queda | Sharpe | Sortino | p Holm | p tentativas |\n|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for l in linhas:
        m = l["metricas"]
        print(f"| {l['setup']} | {l['par']} | {l['sinais']} | {_pct(l['acerto_todos'])} | {l['selecionados']} | {_pct(l['acerto_selecionados'])} | {_pct(l['limite_inferior'])} | {l['auc']:.4f} | "
              f"{m['expectativa']:.4f} | {m['fator_de_lucro']:.3f} | {m['pior_queda']:.1f} | {m['sharpe']:.4f} | {m['sortino']:.4f} | {l['p_ajustado']:.3f} | {l['p_por_tentativas']:.3f} |")
        print("  regimes: " + "; ".join(f"{g} n={d['operacoes']} ac={_pct(d['acerto'])}" for g, d in sorted(l["por_regime"].items())))


def abrir_selado(armazem: ArmazemVelas, registro: Registro, raiz: str, par: str, setup: str, minutos: int, payout: float, pasta: Path) -> None:
    """Teste final de uma hipótese já escolhida. Cada hipótese só pode abrir a área selada uma vez, e a abertura fica registrada."""
    familia = "selado"
    parametros = {"par": par, "setup": setup, "minutos": minutos, "payout": payout}
    if any(l["parametros"] == parametros for l in registro.todos(familia)):
        raise SystemExit("Esta hipótese já abriu a área selada. O resultado vale como está: repetir seria usar o teste para escolher.")
    atributos, v, dados = _base_de_previsao(armazem, par, raiz)
    apostas = apostas_direcao(v, SETUPS[setup](v), minutos, payout).set_index("quando")
    x = atributos.reindex(apostas.index).copy()
    x["regra_direcao"] = apostas["direcao"]
    dev, selado = separar_selado(x.index, SELADO_DESDE)
    y = apostas["ganhou"].astype(int)
    r = {"par": par, "setup": setup, "desde": str(SELADO_DESDE.date()), **avaliar_selado(x[dev], y[dev], x[selado], y[selado], empate(payout))}
    registro.anotar(familia, setup, parametros, dados, r)
    _salvar(pasta, f"selado_{par}", [r])
    print(json.dumps(r, ensure_ascii=False, indent=1, default=float))


def importar_macro(raiz: str, meses: int) -> None:
    """Histórico de resultados e consenso, um dia por chamada e com pausa. Sem hora de chegada: vale o horário do evento."""
    agora = agora_utc().date()
    linhas = FonteResultados().periodo(agora - timedelta(days=meses * 31), agora - timedelta(days=1))
    eventos = ArmazemEventos(raiz)
    eventos.gravar("resultados_macro", "GLOBAL", linhas)
    eventos.compactar(agora_utc())
    print(json.dumps({"eventos": len(linhas), "com_resultado_e_consenso": sum(l["resultado"] is not None and l["consenso"] is not None for l in linhas), "chave": sum(l["classe"] is not None for l in linhas)}), flush=True)


def estudar_macro(armazem: ArmazemVelas, registro: Registro, raiz: str, pares: list[str], pasta: Path) -> None:
    """Reação à surpresa só na área de desenvolvimento. Mostra também as combinações sem resultado: nada é escondido."""
    tabela = surpresas(ArmazemEventos(raiz).ler("resultados_macro", "GLOBAL"))
    tabela = tabela[tabela["ocorrido_em"] < SELADO_DESDE]
    print(f"Eventos com resultado e consenso, até {SELADO_DESDE.date()}: {len(tabela)}; com surpresa padronizada: {int(tabela['surpresa_z'].notna().sum())}.")
    print(tabela["classe"].value_counts().to_dict())
    saida = []
    for par in pares:
        v = armazem.ler(par)
        dados = impressao_dos_dados(v)
        r = reacoes(tabela[tabela["surpresa_z"].notna()].drop_duplicates("ocorrido_em"), v)
        resumo = resumir(r)
        volatilidade = volatilidade_em_torno(tabela.drop_duplicates("ocorrido_em"), v)
        print(f"\n{par}: movimento nos 15 min após o evento {volatilidade['movimento_apos_bps']:.0f} bps contra {volatilidade['movimento_sem_evento_bps']:.0f} bps no mesmo horário sem evento (razão {volatilidade['razao']:.2f}).")
        print("| Evento | Min | Eventos | Correlação | p ajustado | Mesmo sinal | Reação média (bps) | Fortes | Retorno alinhado fortes (bps) |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for l in resumo.itertuples():
            print(f"| {l.classe} | {l.horizonte} | {l.eventos} | {l.correlacao:+.3f} | {l.p_ajustado:.3f} | {_pct(l.mesmo_sinal)} | {l.reacao_media_bps:.0f} | {l.fortes} | {l.retorno_fortes_alinhado_bps:+.1f} |")
            registro.anotar("reacao_macro", l.classe, {"par": par, "horizonte": l.horizonte}, dados, l._asdict())
        saida.append({"par": par, "volatilidade": volatilidade, "resumo": resumo.to_dict("records")})
    _salvar(pasta, "macro", saida)


def estudar_agenda(armazem: ArmazemVelas, registro: Registro, raiz: str, pares: list[str], pasta: Path, horizontes: tuple[int, ...] = (15, 60)) -> None:
    """Saber o que vem pela frente melhora a previsão da volatilidade? Só na área de desenvolvimento, com e sem a agenda."""
    saida = []
    for par in pares:
        atributos, v, dados = _base_de_previsao(armazem, par, raiz)
        for h in horizontes:
            x, y = amostrar(atributos, alvos(v, h), h)
            dev, _ = separar_selado(x.index, SELADO_DESDE)
            r = ganho_da_agenda(x[dev], y.loc[dev, "vol_futura"], h)
            linha = {"par": par, "horizonte": h, **r}
            saida.append(linha)
            registro.anotar("agenda_volatilidade", "LightGBM", {"par": par, "horizonte": h}, dados, linha)
            print(json.dumps(linha, ensure_ascii=False, default=float), flush=True)
    _salvar(pasta, "agenda", saida)


def estudar_combinacoes(armazem: ArmazemVelas, registro: Registro, pares: list[str], payout: float, pasta: Path, tempos: tuple[str, ...] = ("15min", "60min"), horizontes: tuple[int, ...] = (15, 60)) -> None:
    """Combinações e suas partes, com os cortes já fixados. Só desenvolvimento. Tudo entra na correção por múltiplos testes, inclusive o que não deu certo."""
    linhas, sobreposicoes = [], {}
    for par in pares:
        v = armazem.ler(par)
        v = v[v.index < SELADO_DESDE]
        dados = impressao_dos_dados(v)
        for tempo in tempos:
            tabela = sinais(v, tempo)
            sobreposicoes[f"{par}|{tempo}"] = sobreposicao(tabela, list(COMBINACOES)).round(3).to_dict()
            for nome in tabela.columns:
                for h in horizontes:
                    r = {"regra": nome, "tipo": "combinacao" if nome in COMBINACOES else "parte", "par": par, "tempo": tempo, "horizonte": h, **medir_regra(v, tabela[nome], h, payout)}
                    linhas.append(r)
                    registro.anotar("combinacoes", nome, {"par": par, "tempo": tempo, "horizonte": h, "payout": payout}, dados, r)
            print(f"{par} {tempo}: {len(tabela)} velas com algum sinal", flush=True)
    medidas = [l for l in linhas if l["sinais"]]
    for l, p, p50 in zip(medidas, holm([l["p_valor"] for l in medidas]), holm([l["p_contra_50"] for l in medidas])):
        l["p_ajustado"], l["p50_ajustado"] = p, p50
    _salvar(pasta, "combinacoes", linhas)
    _salvar(pasta, "combinacoes_sobreposicao", [sobreposicoes])
    print(f"\nEmpate {_pct(empate(payout))}; {len(medidas)} medições; correção por todas elas. Só combinações com 100 sinais ou mais:")
    print("| Combinação | Par | Tempo | Min | Sinais | Acerto | Lim. inf. | Com atraso | Placebo | 1ª metade | 2ª metade | p>50 aj. | p>empate aj. | Melhor parte |\n|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for l in sorted((l for l in medidas if l["tipo"] == "combinacao" and l["sinais"] >= 100), key=lambda l: -l["limite_inferior"]):
        pares_da_regra = [p["acerto"] for p in medidas if p["regra"] in COMBINACOES[l["regra"]] and p["par"] == l["par"] and p["tempo"] == l["tempo"] and p["horizonte"] == l["horizonte"] and p["sinais"] >= 100]
        melhor = _pct(max(pares_da_regra)) if pares_da_regra else "-"
        print(f"| {l['regra']} | {l['par']} | {l['tempo']} | {l['horizonte']} | {l['sinais']} | {_pct(l['acerto'])} | {_pct(l['limite_inferior'])} | {_pct(l['acerto_com_atraso'])} | {_pct(l['placebo'])} | {_pct(l['acerto_primeira_metade'])} | {_pct(l['acerto_segunda_metade'])} | {l['p50_ajustado']:.3f} | {l['p_ajustado']:.3f} | {melhor} |")
    sem = [l for l in linhas if l["tipo"] == "combinacao" and l["sinais"] < 100]
    print(f"\nCom menos de 100 sinais, sem conclusão: {len(sem)} de {sum(l['tipo'] == 'combinacao' for l in linhas)}.")
    fortes = [l for l in medidas if l["p_ajustado"] < 0.05]
    print(f"Passaram do empate após a correção: {len(fortes)}. " + "; ".join(f"{l['regra']} {l['par']} {l['tempo']} {l['horizonte']}min {_pct(l['acerto'])} n={l['sinais']}" for l in fortes))


def treinar_finais(armazem: ArmazemVelas, registro: Registro, raiz: str, pares: list[str], horizontes: list[int], pasta_modelos: Path) -> None:
    for par in pares:
        atributos, v, dados = _base_de_previsao(armazem, par, raiz)
        for h in horizontes:
            x, y = amostrar(atributos, alvos(v, h), h)
            a = treinar_artefato(pasta_modelos, par, h, x, y["sobe"], dados, commit_atual())
            print(json.dumps({"id": a.manifesto["id"], **{k: a.manifesto["metricas_fora_da_amostra"][k] for k in ("acerto", "auc", "erro_calibracao")}}, ensure_ascii=False), flush=True)


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
    pr = sub.add_parser("prever")
    pr.add_argument("--horizontes", type=int, nargs="+", default=[5, 15, 60])
    pr.add_argument("--payout", type=float, default=0.85)
    me = sub.add_parser("meta")
    me.add_argument("--minutos", type=int, default=15)
    me.add_argument("--payout", type=float, default=0.85)
    sub.add_parser("macro-importar").add_argument("--meses", type=int, default=24)
    sub.add_parser("macro")
    sub.add_parser("agenda")
    sub.add_parser("combinacoes").add_argument("--payout", type=float, default=0.85)
    se = sub.add_parser("selado")
    se.add_argument("par")
    se.add_argument("setup", choices=list(SETUPS))
    se.add_argument("--minutos", type=int, default=15)
    se.add_argument("--payout", type=float, default=0.85)
    tr = sub.add_parser("treinar")
    tr.add_argument("--horizontes", type=int, nargs="+", default=[15, 60])
    tr.add_argument("--modelos", default=os.getenv("MNEME_MODELOS", str(PASTA_DADOS / "modelos")))
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
    elif args.comando == "prever":
        estudar_previsao(armazem, registro, args.raiz, pares, args.horizontes, args.payout, pasta)
    elif args.comando == "meta":
        estudar_meta(armazem, registro, args.raiz, pares, args.minutos, args.payout, pasta)
    elif args.comando == "macro-importar":
        importar_macro(args.raiz, args.meses)
    elif args.comando == "macro":
        estudar_macro(armazem, registro, args.raiz, pares, pasta)
    elif args.comando == "agenda":
        estudar_agenda(armazem, registro, args.raiz, pares, pasta)
    elif args.comando == "combinacoes":
        estudar_combinacoes(armazem, registro, pares, args.payout, pasta)
    elif args.comando == "selado":
        abrir_selado(armazem, registro, args.raiz, args.par, args.setup, args.minutos, args.payout, pasta)
    elif args.comando == "treinar":
        treinar_finais(armazem, registro, args.raiz, pares, args.horizontes, Path(args.modelos))
    else:
        estudar_modelos(armazem, registro, pares, args.horizontes, args.payout, pasta)


if __name__ == "__main__":
    main()

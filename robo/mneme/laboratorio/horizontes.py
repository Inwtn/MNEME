"""Qual horizonte tem vantagem de verdade? Compara ativos, candles, previsões, entradas e expirações, sempre com custos.

Quatro coisas são independentes aqui: o candle em que se decide, o horizonte que o modelo prevê, o atraso até entrar e a expiração da operação.
Muitos sinais não contam a favor de ninguém: o critério é o limite inferior da expectativa líquida.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from .avaliacao import regimes, selecionar_com_passado
from .backtest import continuas
from .previsao import fora_da_amostra
from .robustez import intervalo_por_dias
from .validacao import dobras_walk_forward, empate, intervalo_wilson, p_acima_de

HORIZONTES = (1, 5, 15, 30, 60)
EXPIRACOES = (1, 5, 15, 30, 60)
ATRASOS = (0, 1, 2, 5)
PAYOUTS = (0.75, 0.80, 0.85, 0.90)
# Tabela pública sem desconto, por ponta. O spread e a slippage vêm do livro coletado.
TAXA_SPOT_BPS, TAXA_DERIVATIVO_BPS = 10.0, 5.0


@dataclass(frozen=True)
class Cenario:
    """Em que candle se decide, o que o modelo prevê, quanto se demora para entrar e quanto a operação dura."""
    candle: int
    horizonte: int
    atraso: int = 0
    expiracao: int | None = None

    def __post_init__(self):
        if self.candle < 1 or self.horizonte < 1 or self.atraso < 0 or (self.expiracao is not None and self.expiracao < 1):
            raise ValueError("Cenário inválido.")

    @property
    def duracao(self) -> int:
        return self.expiracao if self.expiracao is not None else self.horizonte


def amostrar_grade(x: pd.DataFrame, y: pd.DataFrame, candle: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Uma linha por candle fechado. Só retira o aquecimento dos indicadores e o que não tem alvo."""
    grade = x.index[(x.index.hour * 60 + x.index.minute + 1) % candle == 0]
    x, y = x.loc[grade], y.loc[grade]
    validas = y["sobe"].notna() & x["v_retorno_240"].notna() & x["v_60min_adx"].notna()
    return x[validas], y[validas]


def validacao_do_cenario(n: int, c: Cenario, dobras: int = 5, embargo: int = 2):
    """Com candle menor que o horizonte os alvos se sobrepõem: a purga em linhas cobre o horizonte inteiro."""
    return dobras_walk_forward(n, dobras, int(np.ceil(c.horizonte / c.candle)), embargo)


def retorno_da_operacao(v: pd.DataFrame, tempos: pd.DatetimeIndex, atraso: int, expiracao: int) -> np.ndarray:
    """Entra na abertura `atraso` minutos depois da vela seguinte ao sinal e sai `expiracao` minutos depois da entrada."""
    c = continuas(v)
    entrada = c["abertura"].shift(-(1 + atraso)).reindex(tempos).to_numpy()
    saida = c["fechamento"].shift(-(atraso + expiracao)).reindex(tempos).to_numpy()
    return saida / entrada - 1


def uma_por_vez(tempos: pd.DatetimeIndex, atraso: int, expiracao: int) -> np.ndarray:
    """Sinais durante uma operação aberta são ignorados. É o número de operações que dá para fazer de verdade."""
    minutos = tempos.as_unit("ns").asi8 // 60_000_000_000
    aceitos = np.zeros(len(minutos), dtype=bool)
    livre = np.iinfo(np.int64).min
    for i, t in enumerate(minutos):
        if t >= livre:
            aceitos[i] = True
            livre = t + atraso + expiracao + 1
    return aceitos


def medir_operacoes(tempos: pd.DatetimeIndex, direcao: np.ndarray, retorno: np.ndarray, custos: dict | None = None, dias_periodo: int | None = None) -> dict:
    """Resultado por operação e por dia. Acerto alto não basta: mostra expectativa, custo e intervalo que sorteia dias inteiros."""
    r = retorno * direcao
    validas = ~np.isnan(r) & (r != 0)
    tempos, direcao, r = tempos[validas], direcao[validas], r[validas]
    n = len(r)
    if n == 0:
        return {"operacoes": 0}
    certos = r > 0
    acerto = float(certos.mean())
    ic = intervalo_por_dias(certos, tempos)
    dias = dias_periodo or max(int(pd.Index(tempos.floor("D")).nunique()), 1)
    trimestres = pd.Series(certos, index=np.asarray(tempos.tz_localize(None).to_period("Q").astype(str)))
    por_trimestre = trimestres.groupby(level=0).agg(["mean", "size"])
    por_trimestre = por_trimestre[por_trimestre["size"] >= 30]
    empate_85 = empate(0.85)
    medio_bps = float(r.mean() * 1e4)
    compras = direcao > 0
    saida = {"operacoes": n, "por_dia": n / dias, "acerto": acerto, "wilson": intervalo_wilson(int(certos.sum()), n)[0], "ic95_dias": list(ic), "p_contra_empate_85": p_acima_de(int(certos.sum()), n, empate_85),
             "retorno_medio_bps": medio_bps, "retorno_compras_bps": float(r[compras].mean() * 1e4) if compras.any() else None, "acerto_compra": float(certos[compras].mean()) if compras.any() else None, "acerto_venda": float(certos[~compras].mean()) if (~compras).any() else None,
             "digital": {str(p): {"expectativa": acerto * p - (1 - acerto), "limite_inferior": ic[0] * p - (1 - ic[0]), "por_dia": (acerto * p - (1 - acerto)) * n / dias} for p in PAYOUTS},
             "trimestres_acima_85": [int((por_trimestre["mean"] > empate_85).sum()), len(por_trimestre)]}
    if custos:
        ida_e_volta = 2 * (custos["meio_spread_bps"] + custos["slippage_bps"])
        custo_derivativo = ida_e_volta + 2 * TAXA_DERIVATIVO_BPS
        custo_spot = ida_e_volta + 2 * TAXA_SPOT_BPS
        saida["derivativo_liquido_bps"] = medio_bps - custo_derivativo
        saida["spot_liquido_bps"] = (saida["retorno_compras_bps"] - custo_spot) if saida["retorno_compras_bps"] is not None else None
        saida["custo_derivativo_bps"], saida["custo_spot_bps"] = custo_derivativo, custo_spot
    return saida


def custos_do_livro(livro: pd.DataFrame, tamanho_usd: float = 1000.0, amostra: int = 3000) -> dict:
    """Spread e slippage medidos: consome o livro até preencher o tamanho, nos dois lados. Só vale para o período coletado."""
    if livro.empty:
        return {"medido": False, "meio_spread_bps": 0.0, "slippage_bps": 0.0, "fotos": 0}
    passo = max(len(livro) // amostra, 1)
    fotos = livro.iloc[::passo]
    deslizes = []
    for f in fotos.itertuples():
        meio = (f.melhor_compra + f.melhor_venda) / 2
        for precos, quantidades, topo in ((f.vendas_precos, f.vendas_qtd, f.melhor_venda), (f.compras_precos, f.compras_qtd, f.melhor_compra)):
            falta, gasto, comprado = tamanho_usd, 0.0, 0.0
            for p, q in zip(precos, quantidades):
                valor = min(falta, p * q)
                gasto += valor
                comprado += valor / p
                falta -= valor
                if falta <= 0:
                    break
            if falta <= 0 and comprado and meio:
                deslizes.append(abs(gasto / comprado - topo) / meio * 1e4)
    return {"medido": True, "meio_spread_bps": float(livro["spread_bps"].mean() / 2), "spread_p95_bps": float(livro["spread_bps"].quantile(0.95)), "slippage_bps": float(np.mean(deslizes)) if deslizes else 0.0,
            "tamanho_usd": tamanho_usd, "fotos": len(fotos), "desde": str(livro["ocorrido_em"].min()), "ate": str(livro["ocorrido_em"].max())}


def prever_cenario(x: pd.DataFrame, y: pd.Series, c: Cenario, criar: Callable, fracao: float = 0.2, dobras: int = 5, embargo: int = 2) -> pd.DataFrame:
    """Previsões fora da amostra, com o corte de confiança vindo só do passado. Guarda o bastante para testar outras entradas e expirações sem treinar de novo."""
    p = fora_da_amostra(criar, x, y, validacao_do_cenario(len(x), c, dobras, embargo))
    selecao = selecionar_com_passado(np.abs(p.prob - 0.5), p.blocos, fracao)
    linhas = x.iloc[p.posicoes]
    return pd.DataFrame({"prob": p.prob.astype("float32"), "real": p.real.astype("float32"), "confiante": selecao, "regime": regimes(linhas).astype("category").to_numpy(),
                         "vol_percentil": linhas["v_60min_volatilidade_percentil"].to_numpy(dtype="float32")}, index=linhas.index)


def avaliar_previsoes(p: pd.DataFrame, v: pd.DataFrame, custos: dict | None, atrasos: tuple[int, ...] = ATRASOS, expiracoes: tuple[int, ...] = EXPIRACOES) -> dict:
    """Mesmas previsões, em toda combinação de atraso e expiração, com uma operação de cada vez."""
    geral = {"previsoes": len(p), "acerto_geral": float(((p["prob"] >= 0.5) == (p["real"] == 1)).mean()), "auc": float(roc_auc_score(p["real"], p["prob"]))}
    dias = max(int(pd.Index(p.index.floor("D")).nunique()), 1)
    conf = p[p["confiante"]]
    tempos = pd.DatetimeIndex(conf.index)
    direcao = np.where(conf["prob"] >= 0.5, 1, -1)
    matriz = []
    for expiracao in expiracoes:
        for atraso in atrasos:
            aceitos = uma_por_vez(tempos, atraso, expiracao)
            r = retorno_da_operacao(v, tempos[aceitos], atraso, expiracao)
            matriz.append({"expiracao": expiracao, "atraso": atraso, **medir_operacoes(tempos[aceitos], direcao[aceitos], r, custos, dias)})
    return {**geral, "matriz": matriz}


def por_condicao(p: pd.DataFrame, v: pd.DataFrame, expiracao: int, minimo: int = 100) -> dict:
    """Acerto dos confiantes por regime, volatilidade e hora. Serve para levantar hipóteses de quando não operar, ainda não para aplicá-las."""
    conf = p[p["confiante"]]
    tempos = pd.DatetimeIndex(conf.index)
    direcao = np.where(conf["prob"] >= 0.5, 1, -1)
    r = retorno_da_operacao(v, tempos, 0, expiracao) * direcao
    tabela = pd.DataFrame({"certo": r > 0, "valido": ~np.isnan(r) & (r != 0), "regime": conf["regime"].astype(str).to_numpy(), "vol": pd.cut(conf["vol_percentil"], [0, 0.25, 0.5, 0.75, 1.0], include_lowest=True, labels=["vol 0-25%", "vol 25-50%", "vol 50-75%", "vol 75-100%"]).astype(str).to_numpy(),
                           "sessao": pd.cut(tempos.hour, [-1, 7, 13, 20, 24], labels=["Ásia 00-07 UTC", "Europa 08-13 UTC", "EUA 14-20 UTC", "Noite 21-23 UTC"]).astype(str)}, index=tempos)
    tabela = tabela[tabela["valido"]]
    saida = {}
    for coluna in ("regime", "vol", "sessao"):
        grupos = tabela.groupby(coluna)["certo"].agg(["mean", "size"])
        saida[coluna] = {str(g): {"acerto": float(l["mean"]), "n": int(l["size"])} for g, l in grupos.iterrows() if l["size"] >= minimo}
    return saida


def regra_de_movimento(v: pd.DataFrame, olhar: int, fracao: float = 0.2, janela_dias: int = 30) -> pd.DataFrame:
    """Regra sem modelo: o movimento de `olhar` minutos foi forte frente aos últimos 30 dias? `reversao` aposta contra ele, `continuacao` a favor. O corte só usa o passado."""
    c = continuas(v)
    movimento = c["fechamento"].pct_change(olhar, fill_method=None)
    grade = c.index[(c.index.hour * 60 + c.index.minute + 1) % olhar == 0]
    m = movimento.reindex(grade)
    tamanho = m.abs()
    corte = tamanho.rolling(int(janela_dias * 1440 / olhar), min_periods=int(5 * 1440 / olhar)).quantile(1 - fracao).shift(1)
    forte = tamanho >= corte
    sinal = -np.sign(m).where(forte, 0.0).fillna(0.0)
    return pd.DataFrame({"reversao": sinal, "continuacao": -sinal}, index=grade)


def medir_regra_de_movimento(v: pd.DataFrame, olhar: int, expiracao: int, atraso: int, custos: dict | None) -> dict:
    regra = regra_de_movimento(v, olhar)
    ativos = regra[regra["reversao"] != 0]
    tempos = pd.DatetimeIndex(ativos.index)
    aceitos = uma_por_vez(tempos, atraso, expiracao)
    dias = max(int(pd.Index(regra.index.floor("D")).nunique()), 1)
    r = retorno_da_operacao(v, tempos[aceitos], atraso, expiracao)
    return {nome: medir_operacoes(tempos[aceitos], ativos[nome].to_numpy()[aceitos], r, custos, dias) for nome in ("reversao", "continuacao")}


def alvo_de_amplitude(v: pd.DataFrame, horizonte: int) -> tuple[pd.Series, pd.Series]:
    """Log da amplitude dos próximos minutos, a partir da vela seguinte, e a mesma medida dos últimos minutos como referência simples. Serve também para 1 minuto."""
    c = continuas(v)
    def amplitude(maximos: pd.Series, minimos: pd.Series) -> pd.Series:
        return np.log(((maximos - minimos) / c["fechamento"]).replace(0, np.nan))
    passada = amplitude(c["maxima"].rolling(horizonte).max(), c["minima"].rolling(horizonte).min())
    return passada.shift(-horizonte), passada


GRUPOS_DE_ATRIBUTOS: dict[str, Callable[[str], bool]] = {
    "agressão": lambda c: c.startswith("f_delta"),
    "volume": lambda c: c.startswith(("f_volume", "f_negocios", "f_tamanho")) or c.endswith("volume_relativo"),
    "VWAP e desvios": lambda c: c.endswith("distancia_vwap_pct"),
    "momentum e exaustão": lambda c: c.endswith(("rsi_14", "macd_hist", "adx", "di_mais", "di_menos", "bb_posicao")) or "dist_ema" in c,
    "volatilidade curta": lambda c: c.endswith(("atr_pct", "bb_largura", "volatilidade_percentil", "largura_percentil")) or c.startswith("v_volatilidade"),
    "estrutura e liquidez": lambda c: c.endswith(("estrutura", "rompimento", "falso_rompimento", "dist_suporte", "dist_resistencia", "consolidacao", "tendencia", "engolfo", "martelo", "estrela")) or "liq_varredura" in c or "wyckoff" in c,
    "outras metodologias": lambda c: c.startswith("m_") and "liq_varredura" not in c and "wyckoff" not in c,
    "outro mercado": lambda c: c.startswith("c_"),
    "derivativos": lambda c: c.startswith("d_"),
    "relógio": lambda c: c.startswith("t_"),
    "eventos e agenda": lambda c: c.startswith("e_"),
    "contexto 4h e diário": lambda c: c.startswith("x_"),
}
BASE_DE_RETORNOS = "v_retorno_"


def _modelo_rapido():
    # Menos árvores que o estudo principal, igual nos dois lados de cada comparação: aqui importa a diferença, não o nível.
    return lgb.LGBMClassifier(n_estimators=120, learning_rate=0.05, num_leaves=15, min_child_samples=200, subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, random_state=0, n_jobs=2, verbose=-1)


def comparar_atributos(x: pd.DataFrame, y: pd.Series, c: Cenario, a: list[str], b: list[str], criar: Callable = _modelo_rapido, dobras: int = 3, sorteios: int = 500) -> dict:
    """Mesmas dobras com os dois conjuntos. Ganho em AUC, com intervalo sorteando dias inteiros. Intervalo com zero: nada demonstrado."""
    if not b or not a:
        return {"amostras": 0}
    pa = fora_da_amostra(criar, x[a], y, validacao_do_cenario(len(x), c, dobras))
    pb = fora_da_amostra(criar, x[b], y, validacao_do_cenario(len(x), c, dobras))
    dias = x.index[pa.posicoes].floor("D").asi8
    unicos, grupos = np.unique(dias, return_inverse=True)
    inicio = np.searchsorted(grupos, np.arange(len(unicos))) if np.all(np.diff(grupos) >= 0) else None
    gerador = np.random.default_rng(0)
    ganhos = []
    limites = np.append(inicio, len(grupos))
    for _ in range(sorteios):
        escolhidos = gerador.integers(0, len(unicos), len(unicos))
        linhas = np.concatenate([np.arange(limites[d], limites[d + 1]) for d in escolhidos])
        if len(np.unique(pa.real[linhas])) > 1:
            ganhos.append(roc_auc_score(pa.real[linhas], pb.prob[linhas]) - roc_auc_score(pa.real[linhas], pa.prob[linhas]))
    auc_a, auc_b = roc_auc_score(pa.real, pa.prob), roc_auc_score(pa.real, pb.prob)
    return {"amostras": len(pa.real), "auc_sem": float(auc_a), "auc_com": float(auc_b), "ganho_auc": float(auc_b - auc_a), "ic95": [float(np.quantile(ganhos, 0.025)), float(np.quantile(ganhos, 0.975))], "demonstrado": bool(np.quantile(ganhos, 0.025) > 0)}


def _sinal_por_etapa(x: pd.DataFrame, a_favor_do_contexto: bool) -> dict[str, pd.Series]:
    """Hipótese de 1h + 15 min + 5 min + 1 min, etapa por etapa. Cortes fixados antes de medir."""
    contexto = x["v_60min_tendencia"].fillna(0)
    lado = contexto if a_favor_do_contexto else -contexto
    regiao = np.where(lado > 0, x["v_15min_dist_suporte"].between(0, 1.0), x["v_15min_dist_resistencia"].between(0, 1.0))
    gatilho = np.where(lado > 0, x["v_5min_rsi_14"] <= 40, x["v_5min_rsi_14"] >= 60)
    refino = np.sign(x["v_retorno_1"].fillna(0)) == np.sign(lado)
    com_regiao = lado.where(regiao, 0.0)
    com_gatilho = com_regiao.where(gatilho, 0.0)
    return {"só contexto 1h": lado, "+ região 15 min": com_regiao, "+ gatilho 5 min": com_gatilho, "+ refino 1 min": com_gatilho.where(refino, 0.0)}


def medir_multi_tempo(x: pd.DataFrame, v: pd.DataFrame, expiracao: int, custos: dict | None) -> list[dict]:
    """A cada filtro somado, o resultado precisa melhorar. Testa operar a favor e contra o contexto de 1h."""
    linhas = []
    dias = max(int(pd.Index(x.index.floor("D")).nunique()), 1)
    for nome, a_favor in (("a favor do contexto", True), ("contra o contexto", False)):
        for etapa, sinal in _sinal_por_etapa(x, a_favor).items():
            ativos = sinal[sinal != 0]
            tempos = pd.DatetimeIndex(ativos.index)
            aceitos = uma_por_vez(tempos, 0, expiracao)
            r = retorno_da_operacao(v, tempos[aceitos], 0, expiracao)
            linhas.append({"sentido": nome, "etapa": etapa, "expiracao": expiracao, **medir_operacoes(tempos[aceitos], ativos.to_numpy()[aceitos], r, custos, dias)})
    return linhas


def desequilibrio_do_livro(livro: pd.DataFrame, v: pd.DataFrame) -> dict:
    """Prévia com pouquíssimos dias: o desequilíbrio do livro no fechamento do minuto e o retorno do minuto seguinte. Não serve para aprovar nada."""
    if livro.empty:
        return {"minutos": 0}
    serie = livro.set_index("ocorrido_em")["desequilibrio_5"].sort_index().resample("1min", label="left").last()
    retorno = continuas(v)["fechamento"].shift(-1).reindex(serie.index) / continuas(v)["abertura"].shift(-1).reindex(serie.index) - 1
    t = pd.DataFrame({"d": serie, "r": retorno}).dropna()
    t = t[t["r"] != 0]
    if len(t) < 100:
        return {"minutos": len(t)}
    forte = t[t["d"].abs() >= t["d"].abs().quantile(0.8)]
    return {"minutos": len(t), "correlacao": float(t["d"].corr(t["r"], method="spearman")), "acerto_geral": float((np.sign(t["d"]) == np.sign(t["r"])).mean()), "acerto_fortes": float((np.sign(forte["d"]) == np.sign(forte["r"])).mean()), "fortes": len(forte), "dias": int(pd.Index(t.index.floor("D")).nunique())}

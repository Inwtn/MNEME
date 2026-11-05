"""Estudo de eventos: como os ativos reagem à surpresa econômica. Mede a reação depois de a informação estar pública, com custo de atraso."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .backtest import continuas
from .validacao import holm


def reacoes(eventos: pd.DataFrame, v: pd.DataFrame, horizontes: tuple[int, ...] = (5, 15, 60), atraso_min: int = 1) -> pd.DataFrame:
    """Para cada divulgação: retorno entre a entrada, `atraso_min` minutos depois, e cada horizonte. Antes: o que o preço já tinha feito."""
    v = continuas(v)
    abertura, fechamento = v["abertura"], v["fechamento"]
    linhas = []
    for e in eventos.itertuples():
        t = e.ocorrido_em.floor("min")
        entrada = t + pd.Timedelta(minutes=atraso_min)
        if entrada not in abertura.index or pd.isna(abertura.get(entrada)):
            continue
        preco = abertura[entrada]
        antes = t - pd.Timedelta(minutes=60)
        linha = {"id": e.id, "ocorrido_em": e.ocorrido_em, "classe": e.classe, "surpresa_z": e.surpresa_z, "antes_60": abertura[t] / fechamento[antes] - 1 if antes in fechamento.index and t in abertura.index else np.nan,
                 "imediato": preco / abertura[t] - 1 if t in abertura.index else np.nan}
        for h in horizontes:
            saida = entrada + pd.Timedelta(minutes=h - 1)
            linha[f"retorno_{h}"] = fechamento[saida] / preco - 1 if saida in fechamento.index else np.nan
            janela = v.loc[entrada:saida]
            linha[f"amplitude_{h}"] = (janela["maxima"].max() - janela["minima"].min()) / preco if len(janela) else np.nan
        linhas.append(linha)
    return pd.DataFrame(linhas)


def resumir(r: pd.DataFrame, horizontes: tuple[int, ...] = (5, 15, 60), minimo: int = 10) -> pd.DataFrame:
    """Por tipo de evento e horizonte: a relação entre surpresa e retorno, com correção por todas as combinações testadas."""
    linhas = []
    for (classe, grupo) in r.dropna(subset=["surpresa_z"]).groupby("classe"):
        for h in horizontes:
            if f"retorno_{h}" not in grupo:
                continue
            g = grupo.dropna(subset=[f"retorno_{h}"])
            if len(g) < minimo or g["surpresa_z"].std() == 0:
                continue
            x, y = g["surpresa_z"].to_numpy(), g[f"retorno_{h}"].to_numpy()
            correlacao, p = stats.spearmanr(x, y)
            sinal = np.sign(x) * np.sign(y)
            forte = np.abs(x) >= 1
            linhas.append({"classe": classe, "horizonte": h, "eventos": len(g), "correlacao": float(correlacao), "p": float(p), "reacao_media_bps": float(np.abs(y).mean() * 1e4),
                           "mesmo_sinal": float((sinal[sinal != 0] > 0).mean()) if (sinal != 0).any() else np.nan, "fortes": int(forte.sum()), "retorno_fortes_alinhado_bps": float((np.sign(x[forte]) * y[forte]).mean() * 1e4) if forte.any() else np.nan,
                           "amplitude_bps": float(g[f"amplitude_{h}"].mean() * 1e4)})
    tabela = pd.DataFrame(linhas)
    if not tabela.empty:
        tabela["p_ajustado"] = holm(tabela["p"].tolist())
    return tabela


def volatilidade_em_torno(eventos: pd.DataFrame, v: pd.DataFrame, minutos: int = 15) -> dict:
    """Movimento logo depois de eventos, comparado ao do mesmo horário em dias sem evento."""
    v = continuas(v)
    retornos = np.log(v["fechamento"]).diff().abs()
    proximos = retornos.rolling(minutos).sum().shift(-minutos)  # soma absoluta dos próximos `minutos`
    apos = proximos.reindex(eventos["ocorrido_em"].dt.floor("min")).dropna()
    momentos = set(eventos["ocorrido_em"].dt.floor("min"))
    hora_evento = apos.index.hour * 60 + apos.index.minute
    comparacao = proximos[pd.Index(proximos.index.hour * 60 + proximos.index.minute).isin(set(hora_evento)) & ~proximos.index.isin(momentos)].dropna()
    return {"eventos": len(apos), "movimento_apos_bps": float(apos.mean() * 1e4) if len(apos) else None, "movimento_sem_evento_bps": float(comparacao.mean() * 1e4) if len(comparacao) else None,
            "razao": float(apos.mean() / comparacao.mean()) if len(apos) and len(comparacao) and comparacao.mean() else None}


def com_macro(x: pd.DataFrame, eventos: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta os atributos macro ao dataset, igual no treino e ao vivo. Sem eventos, as colunas ficam vazias, nunca em zero."""
    from ..dados.resultados_macro import surpresas

    tabela = surpresas(eventos) if not eventos.empty else eventos
    return x.join(atributos_macro(tabela if not tabela.empty else pd.DataFrame(columns=["classe", "ocorrido_em"]), x.index))


def atributos_macro(eventos: pd.DataFrame, indice: pd.DatetimeIndex) -> pd.DataFrame:
    """Em cada vela, só o que já era público: agenda futura de resultados e a última surpresa conhecida. Colunas da família e_."""
    e = eventos.dropna(subset=["classe"]).sort_values("ocorrido_em")
    saida = pd.DataFrame(index=indice)
    if e.empty:
        return saida.assign(e_min_ate_macro=np.nan, e_min_desde_macro=np.nan, e_ultima_surpresa_z=np.nan)
    momentos = pd.DatetimeIndex(e["ocorrido_em"].drop_duplicates()).as_unit("ns").asi8
    agora = (indice + pd.Timedelta(minutes=1)).as_unit("ns").asi8  # a vela fecha um minuto depois de abrir
    pos = np.searchsorted(momentos, agora, side="right")
    limite = 7 * 1440.0
    ate = np.full(len(indice), limite)
    tem = pos < len(momentos)
    ate[tem] = np.minimum((momentos[pos[tem]] - agora[tem]) / 6e10, limite)
    desde = np.full(len(indice), limite)
    tem = pos > 0
    desde[tem] = np.minimum((agora[tem] - momentos[pos[tem] - 1]) / 6e10, limite)
    saida["e_min_ate_macro"], saida["e_min_desde_macro"] = ate, desde
    valores = np.full(len(indice), np.nan)
    if "surpresa_z" in e:
        z = e.dropna(subset=["surpresa_z"]).groupby("ocorrido_em")["surpresa_z"].mean()
        if len(z):
            tempos = pd.DatetimeIndex(z.index).as_unit("ns").asi8
            p = np.searchsorted(tempos, agora, side="right")
            valores[p > 0] = z.to_numpy()[p[p > 0] - 1]
    saida["e_ultima_surpresa_z"] = valores
    return saida

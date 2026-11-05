"""Estudo de eventos: como os ativos reagem à surpresa econômica. Mede a reação depois de a informação estar pública, com custo de atraso."""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy import stats

from ..dados.resultados_macro import EVENTOS_CHAVE, surpresas
from .backtest import continuas
from .validacao import dobras_walk_forward, holm

COLUNAS_AGENDA = ("e_min_ate_macro", "e_min_desde_macro", "e_macro_prox_60", "e_macro_prox_24h", "e_macro_prox_classe", "e_ultima_surpresa_z")


def ganho_da_agenda(x: pd.DataFrame, y: pd.Series, horizonte: int, dobras: int = 5, embargo: int = 2, sorteios: int = 1000) -> dict:
    """Prevê a volatilidade à frente com e sem a agenda, nas mesmas dobras. Mede em tudo e só onde há indicador dentro do horizonte.

    O intervalo sorteia dias inteiros, porque erros do mesmo dia andam juntos. Se ele incluir zero, não há ganho demonstrado.
    """
    validas = y.notna()
    x, y = x[validas], y[validas]
    sem_agenda = [c for c in x.columns if c not in COLUNAS_AGENDA]
    com, sem, real, posicoes = [], [], [], []
    for d in dobras_walk_forward(len(x), dobras, 1, embargo):
        for destino, colunas in ((com, list(x.columns)), (sem, sem_agenda)):
            modelo = lgb.LGBMRegressor(n_estimators=200, learning_rate=0.03, num_leaves=15, min_child_samples=200, subsample=0.7, subsample_freq=1,
                                       colsample_bytree=0.7, random_state=0, n_jobs=2, verbose=-1).fit(x[colunas].iloc[d.treino], y.iloc[d.treino])
            destino.append(modelo.predict(x[colunas].iloc[d.teste]))
        real.append(y.iloc[d.teste].to_numpy())
        posicoes.append(d.teste)
    com, sem, real, posicoes = map(np.concatenate, (com, sem, real, posicoes))
    dias = x.index[posicoes].floor("D").asi8
    janela = (x["e_min_ate_macro"].to_numpy()[posicoes] <= horizonte)
    gerador = np.random.default_rng(0)

    def medir(filtro: np.ndarray) -> dict:
        if filtro.sum() < 30:
            return {"amostras": int(filtro.sum())}
        ec, es = (com[filtro] - real[filtro]) ** 2, (sem[filtro] - real[filtro]) ** 2
        tabela = pd.DataFrame({"dia": dias[filtro], "c": ec, "s": es}).groupby("dia")[["c", "s"]].sum().to_numpy()
        amostras = tabela[gerador.integers(0, len(tabela), (sorteios, len(tabela)))].sum(axis=1)
        ganhos = 1 - amostras[:, 0] / amostras[:, 1]
        total = float(np.var(real[filtro]))
        return {"amostras": int(filtro.sum()), "r2_sem_agenda": 1 - float(es.mean()) / total, "r2_com_agenda": 1 - float(ec.mean()) / total, "ganho": 1 - float(ec.mean() / es.mean()),
                "ganho_ic95": [float(np.quantile(ganhos, 0.025)), float(np.quantile(ganhos, 0.975))]}

    return {"tudo": medir(np.ones(len(real), dtype=bool)), "evento_a_frente": medir(janela), "sem_evento_a_frente": medir(~janela)}


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
    """Acrescenta os atributos macro ao dataset, igual no treino e ao vivo. A agenda futura entra mesmo sem resultado. Sem eventos, as colunas ficam vazias, nunca em zero."""
    if eventos.empty:
        return x.join(atributos_macro(pd.DataFrame(columns=["classe", "ocorrido_em"]), x.index))
    agenda = eventos.dropna(subset=["classe"]).drop_duplicates("id").copy()
    tabela = surpresas(eventos)
    agenda["surpresa_z"] = agenda["id"].map(tabela.set_index("id")["surpresa_z"]) if not tabela.empty else np.nan
    return x.join(atributos_macro(agenda, x.index))


def atributos_macro(eventos: pd.DataFrame, indice: pd.DatetimeIndex) -> pd.DataFrame:
    """Em cada vela, só o que já era público: o que vem pela frente na agenda e a última surpresa conhecida. Colunas da família e_."""
    e = eventos.dropna(subset=["classe"]).sort_values("ocorrido_em")
    saida = pd.DataFrame(index=indice)
    if e.empty:
        return saida.assign(e_min_ate_macro=np.nan, e_min_desde_macro=np.nan, e_macro_prox_60=np.nan, e_macro_prox_24h=np.nan, e_macro_prox_classe=np.nan, e_ultima_surpresa_z=np.nan)
    codigos = {classe: i for i, classe in enumerate(EVENTOS_CHAVE)}
    # Quando sai mais de um indicador no mesmo minuto, vale o primeiro da lista de indicadores.
    por_momento = e.assign(codigo=e["classe"].map(codigos)).groupby("ocorrido_em")["codigo"].min()
    momentos = pd.DatetimeIndex(por_momento.index).as_unit("ns").asi8
    agora = (indice + pd.Timedelta(minutes=1)).as_unit("ns").asi8  # a vela fecha um minuto depois de abrir
    pos = np.searchsorted(momentos, agora, side="right")
    limite = 7 * 1440.0
    # Depois do último evento conhecido a agenda acabou: é falta de dado, e não sete dias de calma.
    ate, classe = np.full(len(indice), np.nan), np.full(len(indice), np.nan)
    tem = pos < len(momentos)
    ate[tem] = np.minimum((momentos[pos[tem]] - agora[tem]) / 6e10, limite)
    classe[tem] = por_momento.to_numpy()[pos[tem]]
    desde = np.full(len(indice), limite)
    tem = pos > 0
    desde[tem] = np.minimum((agora[tem] - momentos[pos[tem] - 1]) / 6e10, limite)
    saida["e_min_ate_macro"], saida["e_min_desde_macro"], saida["e_macro_prox_classe"] = ate, desde, classe
    for nome, minutos in (("e_macro_prox_60", 60), ("e_macro_prox_24h", 1440)):
        saida[nome] = (np.searchsorted(momentos, agora + int(minutos * 6e10), side="right") - pos).astype(float)
    valores = np.full(len(indice), np.nan)
    if "surpresa_z" in e:
        z = e.dropna(subset=["surpresa_z"]).groupby("ocorrido_em")["surpresa_z"].mean()
        if len(z):
            tempos = pd.DatetimeIndex(z.index).as_unit("ns").asi8
            p = np.searchsorted(tempos, agora, side="right")
            valores[p > 0] = z.to_numpy()[p[p > 0] - 1]
    saida["e_ultima_surpresa_z"] = valores
    return saida

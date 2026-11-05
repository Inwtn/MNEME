"""Inteligência social pelo X. Só usa a API oficial, com credencial e teto de gasto; sem os dois, fica desligada e diz isso.

A API cobra por post lido. Por isso a busca é por consultas específicas, e o gasto é registrado antes de cada leitura.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx
import pandas as pd

from .noticias import classificar, limpar

URL_BUSCA = "https://api.x.com/2/tweets/search/recent"
CONSULTAS = {
    "BTC": "(bitcoin OR $BTC) -is:retweet lang:en", "ETH": "(ethereum OR $ETH) -is:retweet lang:en", "SOL": "(solana OR $SOL) -is:retweet lang:en",
    "JUROS_EUA": "(FOMC OR \"Federal Reserve\" OR CPI) -is:retweet lang:en",
}


@dataclass(frozen=True)
class Limites:
    teto_mensal_usd: float = 0.0
    preco_por_post_usd: float = 0.005  # confirmar no painel do X antes de ligar
    posts_por_consulta: int = 10


class GastoExcedido(RuntimeError):
    pass


class FonteX:
    def __init__(self, token: str, limites: Limites, arquivo_gasto: Path | str, cliente: httpx.Client | None = None):
        self.token, self.limites = token, limites
        self.arquivo_gasto = Path(arquivo_gasto)
        self.cliente = cliente or httpx.Client(timeout=20)

    @property
    def ligada(self) -> bool:
        return bool(self.token and self.limites.teto_mensal_usd > 0)

    def gasto_do_mes(self, agora: datetime) -> float:
        if not self.arquivo_gasto.exists():
            return 0.0
        return float(json.loads(self.arquivo_gasto.read_text(encoding="utf-8")).get(f"{agora:%Y-%m}", 0.0))

    def _anotar(self, agora: datetime, valor: float) -> None:
        self.arquivo_gasto.parent.mkdir(parents=True, exist_ok=True)
        dados = json.loads(self.arquivo_gasto.read_text(encoding="utf-8")) if self.arquivo_gasto.exists() else {}
        dados[f"{agora:%Y-%m}"] = dados.get(f"{agora:%Y-%m}", 0.0) + valor
        self.arquivo_gasto.write_text(json.dumps(dados), encoding="utf-8")

    def buscar(self, consulta: str, agora: datetime, desde_id: str | None = None) -> list[dict]:
        """Busca posts recentes. Antes de chamar, confere se o pior caso ainda cabe no teto do mês."""
        if not self.ligada:
            return []
        pior_caso = self.limites.posts_por_consulta * self.limites.preco_por_post_usd
        if self.gasto_do_mes(agora) + pior_caso > self.limites.teto_mensal_usd:
            raise GastoExcedido(f"Teto mensal de US$ {self.limites.teto_mensal_usd:.2f} atingido.")
        params = {"query": consulta, "max_results": max(10, self.limites.posts_por_consulta), "tweet.fields": "created_at,author_id,public_metrics,lang",
                  "expansions": "author_id", "user.fields": "username,verified,public_metrics,created_at"}
        if desde_id:
            params["since_id"] = desde_id
        resposta = self.cliente.get(URL_BUSCA, params=params, headers={"authorization": f"Bearer {self.token}"})
        resposta.raise_for_status()
        corpo = resposta.json()
        posts = ler_posts(corpo, agora)
        self._anotar(agora, len(posts) * self.limites.preco_por_post_usd)
        return posts


def ler_posts(corpo: dict, agora: datetime) -> list[dict]:
    """Normaliza a resposta da API. O texto é tratado como dado externo, e nunca sai como fato."""
    autores = {u["id"]: u for u in (corpo.get("includes") or {}).get("users", [])}
    saida = []
    for p in corpo.get("data") or []:
        autor = autores.get(p.get("author_id"), {})
        texto = limpar(p.get("text"), 1000)
        c = classificar(texto, "", "social")
        metricas = p.get("public_metrics") or {}
        seguidores = (autor.get("public_metrics") or {}).get("followers_count")
        saida.append({"id": str(p["id"]), "ocorrido_em": pd.Timestamp(p["created_at"]), "recebido_em": agora, "fonte": autor.get("username") or str(p.get("author_id")),
                      "categoria": "social", "confiabilidade": "nao_medida", "titulo": texto[:300], "resumo": texto,
                      "url": f"https://x.com/i/status/{p['id']}", "curtidas": metricas.get("like_count", 0), "repostagens": metricas.get("retweet_count", 0),
                      "seguidores": seguidores, "verificado": bool(autor.get("verified")), **{**c, "tipo": c["tipo"] if c["tipo"] != "reportagem" else "post"}})
    return saida


def atividade_coordenada(posts: pd.DataFrame, minimo_autores: int = 3) -> pd.Series:
    """Marca posts quase iguais de autores diferentes, sinal de campanha. Não prova manipulação: só separa para medir."""
    if posts.empty:
        return pd.Series(dtype=bool)
    normal = posts["resumo"].str.lower().str.replace(r"https?://\S+|@\w+|[^a-z0-9$ ]", "", regex=True).str.split().str.join(" ")
    autores = posts.groupby(normal)["fonte"].transform("nunique")
    return autores >= minimo_autores

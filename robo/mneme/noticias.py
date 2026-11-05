"""Notícias: coleta por feeds abertos, classificação por regras e medidas de atenção, sempre pela hora em que a informação chegou.

Texto externo é dado, nunca instrução. Nada aqui decide: tudo vira evidência para o processo central. Sem confirmação, um texto
nunca vira fato; a regra na dúvida é "reportagem", que ainda precisa de outra fonte.
"""

from __future__ import annotations

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx
import numpy as np
import pandas as pd

AGENTE = {"user-agent": "Mozilla/5.0 (compatible; MNEME-research)"}


@dataclass(frozen=True)
class Fonte:
    id: str
    url: str
    categoria: str  # oficial, portal ou cripto
    confiabilidade: str  # alta, media ou baixa; é a nota inicial, a ser medida pelo histórico


FONTES = (
    Fonte("fed", "https://www.federalreserve.gov/feeds/press_all.xml", "oficial", "alta"),
    Fonte("ecb", "https://www.ecb.europa.eu/rss/press.html", "oficial", "alta"),
    Fonte("bea", "https://apps.bea.gov/rss/rss.xml", "oficial", "alta"),
    Fonte("bloomberg", "https://feeds.bloomberg.com/markets/news.rss", "portal", "alta"),
    Fonte("ft", "https://www.ft.com/rss/home", "portal", "alta"),
    Fonte("cnbc", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "portal", "media"),
    Fonte("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "cripto", "media"),
    Fonte("theblock", "https://www.theblock.co/rss.xml", "cripto", "media"),
    Fonte("decrypt", "https://decrypt.co/feed", "cripto", "media"),
    Fonte("cointelegraph", "https://cointelegraph.com/rss", "cripto", "media"),
)

ATIVOS = {
    "BTC": r"\bBTC\b|\bbitcoin\b", "ETH": r"\bETH\b|\bether\b|\bethereum\b", "SOL": r"\bSOL\b|\bsolana\b",
    "EURUSD": r"\bEUR/?USD\b|\beuro\b", "USD": r"\bdollar\b|\bd[oó]lar\b|\bUSD\b|\bDXY\b", "OURO": r"\bgold\b|\bouro\b",
    "JUROS_EUA": r"\bfed\b|\bfomc\b|\bfederal reserve\b|\btreasury yields?\b|\bpowell\b", "ACOES_EUA": r"\bs&p ?500\b|\bnasdaq\b|\bwall street\b",
}
_CASO_EXATO = {"SOL", "ETH", "BTC"}  # "sol" minúsculo é outra palavra em português
TEMAS = {
    "juros": r"\brate (cut|hike)s?\b|\binterest rates?\b|\bjuros\b|\bcopom\b|\bfomc\b", "inflacao": r"\binflation\b|\bcpi\b|\bpce\b|\binfla[cç][aã]o\b|\bipca\b",
    "emprego": r"\bpayrolls?\b|\bjobs report\b|\bunemployment\b|\bemprego\b", "regulacao": r"\bsec\b|\bregulat|\blawsuit\b|\bban\b|\bcftc\b|\bbill\b",
    "etf": r"\betfs?\b", "hack": r"\bhack|\bexploit\b|\bdrain|\bbreach\b", "listagem": r"\blist(s|ing|ed)\b|\bdelist", "geopolitica": r"\bwar\b|\btariffs?\b|\bsanctions?\b|\belection\b|\bguerra\b|\belei[cç]",
    "mineracao_e_rede": r"\bhalving\b|\bmining\b|\bupgrade\b|\bfork\b|\boutage\b",
}
_TIPOS = (
    ("opiniao", r"\bopinion\b|\bopini[aã]o\b|\bwhy i\b|\bi think\b|\bcommentary\b|\bexplained\b|\banalyst says\b|\banalysts? (say|said|think|believe)\b"),
    ("previsao", r"\bprice prediction\b|\bforecast\b|\bcould (hit|reach)\b|\bwill (hit|reach)\b|\bexpected to\b|\bpoised to\b|\bprevis[aã]o\b"),
    ("rumor", r"\brumou?rs?\b|\breportedly\b|\bsources? (say|said)\b|\bunconfirmed\b|\bleak(s|ed)?\b|\bsegundo fontes\b|\bboato\b"),
    ("em_desenvolvimento", r"\bbreaking\b|\bdeveloping\b|\bpreliminary\b|\bparcial\b|\bpreliminar\b|\bprobes?\b|\bmay\b"),
    ("especulacao", r"\bcould\b|\bmight\b|\bspeculat|\bpode\b"),
)
_SUSPEITO = re.compile(r"ignore (all |your |previous )|disregard (all|previous)|system prompt|you are now|ignore suas instru|buy now|100x", re.I)
_POSITIVO = re.compile(r"\b(surge|soar|rally|gain|jump|record high|approve|bullish|inflows?|beats?|sobe|alta|recorde)\w*\b", re.I)
_NEGATIVO = re.compile(r"\b(plunge|crash|drop|slump|hack|exploit|lawsuit|ban|bearish|outflows?|miss(es)?|sell-?off|despenca|queda|cai)\w*\b", re.I)


def limpar(texto: str | None, limite: int = 2000) -> str:
    sem_tags = re.sub(r"<[^>]+>", " ", html.unescape(texto or ""))
    return re.sub(r"\s+", " ", sem_tags).strip()[:limite]


def _ativos(texto: str) -> list[str]:
    achados = []
    for ativo, padrao in ATIVOS.items():
        bandeira = 0 if ativo in _CASO_EXATO else re.I
        # A forma por extenso vale em qualquer caixa; a sigla, só em maiúsculas.
        if re.search(padrao, texto, bandeira) or (ativo in _CASO_EXATO and re.search(padrao.split("|", 1)[1], texto, re.I)):
            achados.append(ativo)
    return achados


def classificar(titulo: str, resumo: str, categoria: str) -> dict:
    """Regras simples e explicáveis. Só comunicado de fonte oficial sai como fato."""
    texto = f"{titulo} {resumo}"
    if categoria == "oficial":
        tipo = "fato"
    else:
        tipo = next((nome for nome, padrao in _TIPOS if re.search(padrao, titulo, re.I)), "reportagem")
    positivos, negativos = len(_POSITIVO.findall(titulo)), len(_NEGATIVO.findall(titulo))
    temas = [t for t, p in TEMAS.items() if re.search(p, texto, re.I)]
    ativos = _ativos(texto)
    return {"tipo": tipo, "ativos": ativos, "temas": temas, "sentimento": int(np.sign(positivos - negativos)),
            "relevante": bool(ativos or temas), "suspeito": bool(_SUSPEITO.search(texto))}


def _data(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        data = parsedate_to_datetime(valor)
    except (TypeError, ValueError):
        try:
            data = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return None
    return data if data.tzinfo else data.replace(tzinfo=timezone.utc)


def ler_feed(corpo: bytes | str, fonte: Fonte, agora: datetime) -> list[dict]:
    """Aceita RSS e Atom. Publicação com data futura ou sem data usa a hora de chegada, que é o que de fato se sabia."""
    raiz = ET.fromstring(corpo)
    itens = []
    for e in raiz.iter():
        nome = e.tag.rsplit("}", 1)[-1]
        if nome not in ("item", "entry"):
            continue
        campos: dict[str, str] = {}
        for filho in e:
            chave = filho.tag.rsplit("}", 1)[-1]
            campos.setdefault(chave, (filho.text or filho.get("href") or ""))
        titulo = limpar(campos.get("title"), 300)
        if not titulo:
            continue
        link = (campos.get("link") or campos.get("guid") or campos.get("id") or titulo).strip()
        publicada = _data(campos.get("pubDate") or campos.get("published") or campos.get("updated") or campos.get("date"))
        if publicada is None or publicada > agora:
            publicada = agora
        resumo = limpar(campos.get("description") or campos.get("summary") or campos.get("encoded"))
        itens.append({"id": hashlib.sha256(link.encode()).hexdigest()[:20], "ocorrido_em": pd.Timestamp(publicada), "recebido_em": agora, "fonte": fonte.id,
                      "categoria": fonte.categoria, "confiabilidade": fonte.confiabilidade, "titulo": titulo, "resumo": resumo, "url": link,
                      **classificar(titulo, resumo, fonte.categoria)})
    return itens


class ColetorNoticias:
    def __init__(self, cliente: httpx.Client | None = None, fontes: tuple[Fonte, ...] = FONTES):
        self.cliente = cliente or httpx.Client(timeout=20, headers=AGENTE, follow_redirects=True)
        self.fontes = fontes

    def coletar(self, agora: datetime) -> tuple[list[dict], dict[str, str]]:
        """Devolve as notícias e o estado de cada fonte. Uma fonte fora do ar não atrapalha as outras."""
        noticias, estado = [], {}
        for fonte in self.fontes:
            try:
                resposta = self.cliente.get(fonte.url)
                resposta.raise_for_status()
                itens = ler_feed(resposta.content, fonte, agora)
                noticias.extend(itens)
                estado[fonte.id] = f"ok: {len(itens)}"
            except (httpx.HTTPError, ET.ParseError) as erro:
                estado[fonte.id] = f"falhou: {erro.__class__.__name__}"
        return noticias, estado


def agrupar_eventos(noticias: pd.DataFrame, parecido: float = 0.6, janela_horas: int = 24) -> pd.Series:
    """Agrupa manchetes sobre o mesmo evento, na ordem de chegada. Várias fontes iguais contam como um evento, com confirmação."""
    palavras = noticias["titulo"].str.lower().str.findall(r"[a-zà-ú0-9]{4,}").map(set)
    grupos, ativos = [], []
    tempos = noticias["recebido_em"].fillna(noticias["ocorrido_em"])
    for i, (conjunto, tempo) in enumerate(zip(palavras, tempos)):
        ativos = [g for g in ativos if tempo - g[2] <= pd.Timedelta(hours=janela_horas)]
        grupo = next((g[0] for g in ativos if conjunto and len(conjunto & g[1]) / len(conjunto | g[1]) >= parecido), None)
        if grupo is None:
            grupo = i
            ativos.append((grupo, conjunto, tempo))
        grupos.append(grupo)
    return pd.Series(grupos, index=noticias.index)


def medidas_de_atencao(textos: pd.DataFrame, ativo: str, indice: pd.DatetimeIndex, janela: str = "60min", base_dias: int = 7) -> pd.DataFrame:
    """Atenção a um ativo em cada instante, só com o que já tinha chegado: volume, anomalia, sentimento, fontes e rumores.

    Serve a notícias e a redes sociais. Muitas menções de poucos autores aparecem em `concentracao`: volume não é relevância.
    """
    colunas = ["mencoes", "anomalia", "sentimento", "fontes", "concentracao", "fracao_rumor"]
    vazio = pd.DataFrame(0.0, index=indice, columns=colunas)
    if textos.empty:
        return vazio
    sobre = textos[textos["ativos"].map(lambda a: ativo in list(a))]
    if sobre.empty:
        return vazio
    chegada = sobre["recebido_em"].fillna(sobre["ocorrido_em"])
    tabela = pd.DataFrame({"um": 1.0, "sentimento": sobre["sentimento"].to_numpy(dtype=float), "rumor": sobre["tipo"].isin(["rumor", "especulacao"]).to_numpy(dtype=float),
                           "fonte": sobre["fonte"].to_numpy()}, index=pd.DatetimeIndex(chegada)).sort_index()
    largura = pd.Timedelta(janela)
    base = pd.Timedelta(days=base_dias)
    tempos = tabela.index.as_unit("ns").asi8
    linhas = []
    for t in indice:
        fim = np.searchsorted(tempos, pd.Timestamp(t).value, side="right")
        ini = np.searchsorted(tempos, (t - largura).value, side="right")
        ini_base = np.searchsorted(tempos, (t - base).value, side="right")
        n = fim - ini
        media_base = max(fim - ini_base, 0) * largura / base
        desvio = np.sqrt(max(media_base, 1.0))
        trecho = tabela.iloc[ini:fim]
        contagem = trecho["fonte"].value_counts()
        linhas.append((float(n), float((n - media_base) / desvio), float(trecho["sentimento"].mean()) if n else 0.0, float(len(contagem)),
                       float(contagem.iloc[0] / n) if n else 0.0, float(trecho["rumor"].mean()) if n else 0.0))
    return pd.DataFrame(linhas, index=indice, columns=colunas)

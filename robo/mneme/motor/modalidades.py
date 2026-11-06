"""O que muda de um mercado para outro: payout e expiração, ou stop, alvo e custo. A arquitetura é uma só, e cada estratégia é medida na própria modalidade."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ExpiracaoFixa:
    """CALL ou PUT com prazo definido. Sem stop e sem alvo. O payout é hipótese até ser medido na corretora."""
    payout: float
    payout_medido: bool = False
    tipo: str = "expiracao_fixa"

    @property
    def empate(self) -> float:
        return 1 / (1 + self.payout)

    def permite(self, direcao: int) -> bool:
        return direcao in (1, -1)

    def expectativa(self, evidencia: dict) -> float | None:
        """Em unidades de aposta por operação: ganha o payout ou perde a aposta inteira."""
        acerto = evidencia.get("acerto")
        return None if acerto is None else acerto * self.payout - (1 - acerto)


@dataclass(frozen=True)
class ComStop:
    """Posição com stop, alvo e tempo máximo. `vende` diz se dá para ficar vendido: à vista só compra. O custo é hipótese até ser medido."""
    custo_bps: float
    stop_atr: float
    alvo_atr: float
    vende: bool
    custo_medido: bool = False
    tipo: str = "com_stop"

    def permite(self, direcao: int) -> bool:
        return direcao == 1 or (direcao == -1 and self.vende)

    def expectativa(self, evidencia: dict) -> float | None:
        """Em unidades de risco (R) por operação, já com o custo desta modalidade."""
        bruto, r_por_bps = evidencia.get("r_bruto"), evidencia.get("r_por_bps")
        return None if bruto is None or r_por_bps is None else bruto - self.custo_bps * r_por_bps


Modalidade = ExpiracaoFixa | ComStop


@dataclass(frozen=True)
class Estrategia:
    """Candle é onde se decide e expiração é quanto a operação dura. São coisas separadas."""
    mercado: str
    ativo: str
    candle: int
    expiracao: int
    modalidade: Modalidade
    fracao: float = 0.1

    @property
    def nome(self) -> str:
        return f"{self.ativo}|{self.modalidade.tipo}|{self.candle}m|{self.expiracao}m"

    @property
    def arquivo(self) -> str:
        return self.nome.replace("|", "_") + ".json"


@dataclass(frozen=True)
class Limites:
    """Cada carteira simulada é de uma estratégia, para elas competirem medidas. Sem valor em algum campo, o Risk Engine recusa."""
    meta_dia_pct: float | None = None
    perda_dia_pct: float | None = None
    max_operacoes_dia: int | None = None
    max_simultaneas_total: int | None = None
    max_perdas_seguidas: int | None = None
    drawdown_max_pct: float | None = None
    idade_maxima_dados_min: float | None = None


@dataclass(frozen=True)
class Configuracao:
    modo: str
    banca: float
    risco_por_operacao: float
    min_operacoes_evidencia: int
    limites: Limites
    estrategias: tuple[Estrategia, ...]


def _modalidade(m: dict) -> Modalidade:
    if m["tipo"] == "expiracao_fixa":
        return ExpiracaoFixa(float(m["payout"]), bool(m.get("payout_medido", False)))
    if m["tipo"] == "com_stop":
        return ComStop(float(m["custo_bps"]), float(m["stop_atr"]), float(m["alvo_atr"]), bool(m["vende"]), bool(m.get("custo_medido", False)))
    raise ValueError(f"Modalidade desconhecida: {m['tipo']}")


def carregar_configuracao(caminho: Path | str) -> Configuracao | None:
    """Sem arquivo, o robô só observa: nenhum valor de estratégia vive no código."""
    caminho = Path(caminho)
    if not caminho.exists():
        return None
    d = json.loads(caminho.read_text(encoding="utf-8"))
    estrategias = []
    for mercado in d["mercados"]:
        for ativo in mercado["ativos"]:
            for m in mercado["modalidades"]:
                estrategias.append(Estrategia(mercado["mercado"], ativo, int(m["candle"]), int(m["expiracao"]), _modalidade(m), float(m.get("fracao", 0.1))))
    return Configuracao(d["modo"], float(d["banca"]), float(d["risco_por_operacao"]), int(d["min_operacoes_evidencia"]), Limites(**d["limites"]), tuple(estrategias))


def liquidar_fixa(v: pd.DataFrame, entrada_em: pd.Timestamp, expiracao: int, direcao: int, payout: float) -> dict | None:
    """Entra na abertura e fecha no fechamento do último minuto do prazo. Empate devolve a aposta. Sem preço nos dois pontos, não apura."""
    fim = entrada_em + pd.Timedelta(minutes=expiracao - 1)
    if entrada_em not in v.index or fim not in v.index:
        return None
    entrada, saida = float(v.at[entrada_em, "abertura"]), float(v.at[fim, "fechamento"])
    variacao = (saida - entrada) * direcao
    resultado = "ganho" if variacao > 0 else "perda" if variacao < 0 else "empate"
    return {"resultado": resultado, "pnl": payout if resultado == "ganho" else -1.0 if resultado == "perda" else 0.0, "preco_entrada": entrada, "preco_saida": saida, "encerrado_por": "expiracao"}


def liquidar_stop(v: pd.DataFrame, entrada_em: pd.Timestamp, tempo_max: int, direcao: int, distancia_stop: float, distancia_alvo: float, custo_bps: float) -> dict | None:
    """Stop e alvo contam a partir da entrada real. Se os dois caem no mesmo minuto, vale o stop: no minuto não dá para saber a ordem, e o pior caso é o honesto."""
    fim = entrada_em + pd.Timedelta(minutes=tempo_max - 1)
    trecho = v[(v.index >= entrada_em) & (v.index <= fim)]
    if trecho.empty or trecho.index[0] != entrada_em or distancia_stop <= 0:
        return None
    entrada = float(trecho["abertura"].iloc[0])
    stop, alvo = entrada - direcao * distancia_stop, entrada + direcao * distancia_alvo
    maximas, minimas = trecho["maxima"].to_numpy(), trecho["minima"].to_numpy()
    bateu_stop = minimas <= stop if direcao == 1 else maximas >= stop
    bateu_alvo = maximas >= alvo if direcao == 1 else minimas <= alvo
    i_stop = int(np.argmax(bateu_stop)) if bateu_stop.any() else None
    i_alvo = int(np.argmax(bateu_alvo)) if bateu_alvo.any() else None
    if i_stop is not None and (i_alvo is None or i_stop <= i_alvo):
        saida, motivo = stop, "stop"
    elif i_alvo is not None:
        saida, motivo = alvo, "alvo"
    elif trecho.index[-1] == fim:
        saida, motivo = float(trecho["fechamento"].iloc[-1]), "tempo"
    else:
        return None  # o prazo ainda não terminou nas velas disponíveis
    custo_r = custo_bps / 1e4 * entrada / distancia_stop
    bruto = (saida - entrada) * direcao / distancia_stop
    pnl = bruto - custo_r
    return {"resultado": "ganho" if pnl > 0 else "perda", "pnl": pnl, "preco_entrada": entrada, "preco_saida": saida, "encerrado_por": motivo, "pnl_bruto": bruto, "custo_r": custo_r}


def amplitude_media(v: pd.DataFrame, candle: int, periodo: int = 14) -> pd.Series:
    """Amplitude média dos últimos candles, medida só com velas já fechadas. É o ATR sem gap, que serve para qualquer ativo."""
    amplitude = v["maxima"].rolling(candle).max() - v["minima"].rolling(candle).min()
    grade = amplitude[(amplitude.index.hour * 60 + amplitude.index.minute + 1) % candle == 0]
    return grade.rolling(periodo).mean()

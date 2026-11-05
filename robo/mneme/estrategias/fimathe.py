"""Interpretação experimental de canais do laboratório local, somente para simulação.

O sinal usa fechamentos; a entrada acontece na próxima abertura contígua. Não reproduz
toda a metodologia discricionária do autor nem o emulador de ordens do TradingView.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from math import floor, isfinite

BRASILIA = timezone(timedelta(hours=-3))


@dataclass(frozen=True)
class RegraFimathe:
    timeframe_minutes: int
    channel_candles: int
    marking: str
    initial_balance: float
    risk_pct: float
    reward_risk: float
    contract_size: float
    min_lots: float
    max_lots: float
    lot_step: float
    spread: float
    slippage: float
    commission_per_lot: float
    max_exposure_pct: float
    daily_profit_target_pct: float
    daily_loss_limit_pct: float
    csv_utc_offset_minutes: int

    @classmethod
    def das_configuracoes(cls, data: dict) -> RegraFimathe | None:
        if any(data.get(k) is None or data.get(k) == "" for k in cls.__dataclass_fields__):
            return None  # Sem configuração completa, só observa.
        values = {}
        for name in cls.__dataclass_fields__:
            value = data[name]
            if name == "marking":
                if value not in ("wicks", "bodies"):
                    raise ValueError("Marcação deve ser pavios ou corpos.")
            else:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                    raise ValueError(f"Campo numérico inválido: {name}.")
                if abs(value) > 1e12:
                    raise ValueError(f"Valor fora do limite do laboratório: {name}.")
                if name in ("timeframe_minutes", "channel_candles", "csv_utc_offset_minutes"):
                    if int(value) != value:
                        raise ValueError(f"Use um inteiro em {name}.")
                    value = int(value)
                if name in ("spread", "slippage", "commission_per_lot"):
                    if value < 0:
                        raise ValueError(f"Custo negativo em {name}.")
                elif name == "csv_utc_offset_minutes":
                    if not -840 <= value <= 840:
                        raise ValueError("Fuso fora do intervalo UTC−14 a UTC+14.")
                elif value <= 0:
                    raise ValueError(f"Preencha um valor positivo em {name}.")
            values[name] = value
        rule = cls(**values)
        if rule.timeframe_minutes not in (1, 5, 15) or not 2 <= rule.channel_candles <= 100:
            raise ValueError("Use M1, M5 ou M15 e entre 2 e 100 velas de referência.")
        if rule.risk_pct > 10 or rule.reward_risk > 20 or rule.max_exposure_pct > 100:
            raise ValueError("Risco máximo 10%, alvo máximo 20 R e exposição máxima 100%.")
        if max(rule.daily_profit_target_pct, rule.daily_loss_limit_pct) > 100:
            raise ValueError("Limites diários devem ser até 100%.")
        if rule.min_lots > rule.max_lots or rule.lot_step > rule.max_lots:
            raise ValueError("Lotes mínimo, máximo e passo incompatíveis.")
        if min(rule.min_lots, rule.lot_step, rule.contract_size) < 1e-8:
            raise ValueError("Contrato, lote mínimo e passo devem ser pelo menos 0,00000001.")
        return rule


@dataclass(frozen=True)
class VelaFimathe:
    time: datetime
    open: float
    high: float
    low: float
    close: float


def simular(velas: list[VelaFimathe], regra: RegraFimathe | None) -> dict:
    """Replay sequencial. Stop primeiro se stop e alvo tocam na mesma vela."""
    if regra is None:
        return {"status": "observacao", "motivo": "Complete a regra em Configurações → Fimathe.", "trades": []}
    r = regra
    delta = timedelta(minutes=r.timeframe_minutes)
    caixa, pico, dd = r.initial_balance, r.initial_balance, 0.0
    posicao = pendente = canal = None
    anteriores = deque(maxlen=r.channel_candles)
    trades, curva, decisoes, sinais = [], [], [], []
    dia, abertura_dia, travado = None, caixa, False
    total_decisoes = 0

    def registrar(vela, motivo):
        nonlocal total_decisoes
        total_decisoes += 1
        decisoes.append({"time": (vela.time + delta).isoformat(), "motivo": motivo})
        if len(decisoes) > 500:
            del decisoes[0]

    def marcar(preco):
        if posicao is None:
            return caixa
        saida = preco if posicao["side"] == "buy" else preco + r.spread
        direcao = 1 if posicao["side"] == "buy" else -1
        return caixa + direcao * (saida - posicao["entry"]) * posicao["lots"] * r.contract_size - r.commission_per_lot * posicao["lots"]

    for i, v in enumerate(velas):
        if v.time.tzinfo is None or any(not isfinite(p) or p <= 0 for p in (v.open, v.high, v.low, v.close)):
            raise ValueError("Vela sem fuso ou com preço inválido.")
        if v.high < max(v.open, v.close, v.low) or v.low > min(v.open, v.close):
            raise ValueError("Máxima ou mínima incoerente.")
        if i and (v.time <= velas[i - 1].time or (v.time - velas[i - 1].time) % delta != timedelta(0)):
            raise ValueError("Velas duplicadas, fora de ordem ou incompatíveis com o intervalo configurado.")
        novo_dia = v.time.astimezone(BRASILIA).date().isoformat()
        if dia != novo_dia:
            dia, abertura_dia, travado = novo_dia, marcar(v.open), False

        if pendente:
            side, stop, quando = pendente
            pendente = None
            if travado or quando != v.time:
                registrar(v, "Entrada descartada: limite diário ou lacuna após o sinal.")
            else:
                entry = v.open + r.spread + r.slippage if side == "buy" else v.open - r.slippage
                distance = (entry - stop) if side == "buy" else (stop - entry)
                quote = v.open if side == "buy" else v.open + r.spread
                valid = (stop < quote if side == "buy" else stop > quote) and entry > 0
                loss_per_lot = (distance + r.slippage) * r.contract_size + 2 * r.commission_per_lot
                budget = max(0, caixa) * r.risk_pct / 100
                exposure = max(0, caixa) * r.max_exposure_pct / 100
                lots = floor((min(budget / loss_per_lot, exposure / (entry * r.contract_size), r.max_lots) + 1e-12) / r.lot_step) * r.lot_step if valid and loss_per_lot > 0 else 0
                if lots < r.min_lots or lots * loss_per_lot > budget + 1e-8:
                    registrar(v, "Entrada bloqueada: stop inválido, exposição ou lote mínimo excede o risco.")
                else:
                    lots = round(lots, 10)
                    posicao = {"side": side, "entry": entry, "stop": stop,
                               "target": entry + distance * r.reward_risk * (1 if side == "buy" else -1),
                               "lots": lots, "opened_at": v.time.isoformat(), "planned_risk": lots * loss_per_lot,
                               "equity_before_entry": caixa}
                    caixa -= r.commission_per_lot * lots

        encerrou = False
        if posicao:
            p = posicao
            buy = p["side"] == "buy"
            lo, hi, op = (v.low, v.high, v.open) if buy else (v.low + r.spread, v.high + r.spread, v.open + r.spread)
            stop = lo <= p["stop"] if buy else hi >= p["stop"]
            alvo = hi >= p["target"] if buy else lo <= p["target"]
            if stop or alvo:
                saida = (min(p["stop"], op) if buy else max(p["stop"], op)) if stop else p["target"]
                saida += -r.slippage if buy else r.slippage
                bruto = (saida - p["entry"]) * (1 if buy else -1) * p["lots"] * r.contract_size
                taxas = 2 * r.commission_per_lot * p["lots"]
                caixa += bruto - taxas / 2
                trades.append({**p, "exit": saida, "closed_at": (v.time + delta).isoformat(),
                               "profit": bruto - taxas, "fees": taxas,
                               "reason": "stop_ambiguo" if stop and alvo else "stop" if stop else "alvo"})
                posicao, encerrou = None, True
        patrimonio = marcar(v.close)
        pico = max(pico, patrimonio)
        dd = max(dd, (pico - patrimonio) / pico * 100)
        retorno_dia = (patrimonio / abertura_dia - 1) * 100 if abertura_dia > 0 else -100
        if retorno_dia >= r.daily_profit_target_pct or retorno_dia <= -r.daily_loss_limit_pct or patrimonio <= 0:
            travado = True  # Continua conferindo as saídas; a trava só libera no dia seguinte.
        curva.append({"time": (v.time + delta).isoformat(), "equity": patrimonio, "day": dia, "entries_blocked": travado})

        anteriores.append(v)
        if canal is None or encerrou or canal[0] <= canal[1]:
            if len(anteriores) == r.channel_candles:
                high = max(max(b.open, b.close) if r.marking == "bodies" else b.high for b in anteriores)
                low = min(min(b.open, b.close) if r.marking == "bodies" else b.low for b in anteriores)
                canal = (high, low)
            continue  # Nunca opera a vela usada para formar/remarcar o canal.
        if posicao or travado or not i:
            continue
        if v.time - velas[i - 1].time != delta:
            registrar(v, "Sem sinal: falta a vela anterior para confirmar o cruzamento.")
            continue
        high, low = canal
        amplitude = high - low
        if velas[i - 1].close <= high + amplitude < v.close:
            pendente = ("buy", low, v.time + delta)
        elif velas[i - 1].close >= low - amplitude > v.close:
            pendente = ("sell", high, v.time + delta)
        if pendente:
            sinais.append({"time": (v.time + delta).isoformat(), "side": pendente[0]})

    ganhos = sum(t["profit"] > 0 for t in trades)
    lucro = sum(t["profit"] for t in trades)
    positivo = sum(max(t["profit"], 0) for t in trades)
    negativo = -sum(min(t["profit"], 0) for t in trades)
    return {"status": "experimental", "mode": "paper", "strategy": "fimathe-experimental-v1",
            "settings": asdict(r), "trades": trades, "position": posicao, "pending_signal": bool(pendente),
            "channel": {"high": canal[0], "low": canal[1]} if canal else None,
            "metrics": {"closed": len(trades), "wins": ganhos, "accuracy_pct": ganhos / len(trades) * 100 if trades else None,
                        "net_profit": lucro, "balance": caixa, "equity": curva[-1]["equity"] if curva else caixa,
                        "profit_factor": positivo / negativo if negativo else None, "max_drawdown_pct": dd,
                        "expectancy": lucro / len(trades) if trades else None},
            "curve": curva, "signals": sinais, "decisions": decisoes, "decision_count": total_decisoes,
            "validation": "Não validada fora da amostra; nenhuma promoção automática para dinheiro real."}

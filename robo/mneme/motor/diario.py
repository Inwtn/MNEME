"""Diário operacional e contexto assíncrono, em SQLite. Toda decisão fica registrada, operada ou não, e tudo é apurado: sinal ruim não some do placar."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from ..carteira import dia_brasilia
from ..laboratorio.validacao import intervalo_wilson

ESQUEMA = """
CREATE TABLE IF NOT EXISTS decisoes (
    chave TEXT PRIMARY KEY, estrategia TEXT NOT NULL, mercado TEXT NOT NULL, ativo TEXT NOT NULL, modalidade TEXT NOT NULL,
    vela TEXT NOT NULL, decidido_em TEXT NOT NULL, latencia_s REAL NOT NULL, dia TEXT NOT NULL,
    direcao INTEGER NOT NULL, forca REAL NOT NULL, expectativa REAL, evidencia TEXT NOT NULL, motivo TEXT NOT NULL,
    motivos_recusa TEXT NOT NULL, contexto TEXT NOT NULL, sinal TEXT NOT NULL, explicacao TEXT,
    tipo TEXT NOT NULL CHECK (tipo IN ('operada', 'sombra')), tamanho REAL NOT NULL,
    situacao TEXT NOT NULL CHECK (situacao IN ('aberta', 'encerrada', 'sem_preco')),
    resultado TEXT, pnl REAL, preco_entrada REAL, preco_saida REAL, encerrado_por TEXT, encerrado_em TEXT, dia_encerramento TEXT
);
CREATE INDEX IF NOT EXISTS decisoes_abertas ON decisoes (situacao, ativo);
CREATE INDEX IF NOT EXISTS decisoes_estrategia ON decisoes (estrategia, tipo, situacao);
CREATE TABLE IF NOT EXISTS contexto (
    id TEXT PRIMARY KEY, ativo TEXT NOT NULL, tipo TEXT NOT NULL, valor TEXT NOT NULL, origem TEXT NOT NULL, criado_em TEXT NOT NULL, valido_ate TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS contexto_vigente ON contexto (ativo, valido_ate);
"""


class Diario:
    def __init__(self, caminho: Path | str):
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(caminho, timeout=30)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript(ESQUEMA)
        self.con.commit()

    def conhecida(self, chave: str) -> bool:
        return self.con.execute("SELECT 1 FROM decisoes WHERE chave = ?", (chave,)).fetchone() is not None

    def registrar(self, *, chave: str, estrategia: str, mercado: str, ativo: str, modalidade: str, vela: pd.Timestamp, decidido_em: pd.Timestamp, latencia_s: float, direcao: int, forca: float, expectativa: float | None,
                  evidencia: dict, motivo: str, motivos_recusa: tuple[str, ...], contexto: tuple[dict, ...], sinal: dict, tipo: str, tamanho: float) -> bool:
        """Só grava uma vez por chave. Devolve se gravou."""
        cursor = self.con.execute("INSERT OR IGNORE INTO decisoes (chave, estrategia, mercado, ativo, modalidade, vela, decidido_em, latencia_s, dia, direcao, forca, expectativa, evidencia, motivo, motivos_recusa, contexto, sinal, tipo, tamanho, situacao) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'aberta')",
                                  (chave, estrategia, mercado, ativo, modalidade, vela.isoformat(), decidido_em.isoformat(), latencia_s, dia_brasilia(decidido_em.to_pydatetime()), direcao, forca, expectativa, json.dumps(evidencia, ensure_ascii=False, default=float), motivo,
                                   json.dumps(list(motivos_recusa), ensure_ascii=False), json.dumps(list(contexto), ensure_ascii=False), json.dumps(sinal, ensure_ascii=False), tipo, tamanho))
        self.con.commit()
        return cursor.rowcount == 1

    def abertas(self) -> list[sqlite3.Row]:
        return self.con.execute("SELECT * FROM decisoes WHERE situacao = 'aberta' ORDER BY ativo").fetchall()

    def encerrar(self, chave: str, apurado: dict | None, agora: pd.Timestamp) -> None:
        """O pnl guardado já é o da operação em unidades da carteira: resultado por unidade vezes o tamanho aprovado."""
        linha = self.con.execute("SELECT tamanho FROM decisoes WHERE chave = ?", (chave,)).fetchone()
        dia = dia_brasilia(agora.to_pydatetime())
        if apurado is None:
            self.con.execute("UPDATE decisoes SET situacao = 'sem_preco', encerrado_em = ?, dia_encerramento = ? WHERE chave = ?", (agora.isoformat(), dia, chave))
        else:
            self.con.execute("UPDATE decisoes SET situacao = 'encerrada', resultado = ?, pnl = ?, preco_entrada = ?, preco_saida = ?, encerrado_por = ?, encerrado_em = ?, dia_encerramento = ? WHERE chave = ?",
                             (apurado["resultado"], apurado["pnl"] * linha["tamanho"], apurado["preco_entrada"], apurado["preco_saida"], apurado["encerrado_por"], agora.isoformat(), dia, chave))
        self.con.commit()

    def situacao_da_estrategia(self, estrategia: str, agora: pd.Timestamp, banca: float) -> dict:
        """Só as operadas entram no risco. A sombra é medição e não gasta nada."""
        dia = dia_brasilia(agora.to_pydatetime())
        q = self.con.execute
        operacoes_hoje = q("SELECT COUNT(*) FROM decisoes WHERE estrategia = ? AND tipo = 'operada' AND dia = ?", (estrategia, dia)).fetchone()[0]
        aberta = q("SELECT 1 FROM decisoes WHERE estrategia = ? AND tipo = 'operada' AND situacao = 'aberta' LIMIT 1", (estrategia,)).fetchone() is not None
        abertas_total = q("SELECT COUNT(*) FROM decisoes WHERE tipo = 'operada' AND situacao = 'aberta'").fetchone()[0]
        hoje = q("SELECT COALESCE(SUM(pnl), 0) FROM decisoes WHERE estrategia = ? AND tipo = 'operada' AND situacao = 'encerrada' AND dia_encerramento = ?", (estrategia, dia)).fetchone()[0]
        perdas = 0
        for linha in q("SELECT resultado FROM decisoes WHERE estrategia = ? AND tipo = 'operada' AND situacao = 'encerrada' AND dia_encerramento = ? ORDER BY encerrado_em DESC, vela DESC", (estrategia, dia)):
            if linha["resultado"] != "perda":
                break
            perdas += 1
        saldo = pico = banca
        for linha in q("SELECT pnl FROM decisoes WHERE estrategia = ? AND tipo = 'operada' AND situacao = 'encerrada' ORDER BY encerrado_em, vela", (estrategia,)):
            saldo += linha["pnl"]
            pico = max(pico, saldo)
        return {"operacoes_hoje": operacoes_hoje, "aberta_na_estrategia": aberta, "abertas_total": abertas_total, "retorno_dia_pct": hoje / banca * 100, "perdas_seguidas": perdas, "drawdown_pct": (pico - saldo) / pico * 100 if pico > 0 else 100.0}

    def placar(self) -> list[dict]:
        saida = []
        for g in self.con.execute("SELECT DISTINCT estrategia, tipo FROM decisoes").fetchall():
            linhas = self.con.execute("SELECT resultado, pnl, latencia_s, situacao FROM decisoes WHERE estrategia = ? AND tipo = ?", (g["estrategia"], g["tipo"])).fetchall()
            fechadas = [l for l in linhas if l["situacao"] == "encerrada" and l["resultado"] != "empate"]
            ganhos = sum(l["resultado"] == "ganho" for l in fechadas)
            saida.append({"estrategia": g["estrategia"], "tipo": g["tipo"], "operacoes": len(fechadas), "ganhos": ganhos, "abertas": sum(l["situacao"] == "aberta" for l in linhas), "sem_preco": sum(l["situacao"] == "sem_preco" for l in linhas),
                          "acerto": ganhos / len(fechadas) if fechadas else None, "limite_inferior": intervalo_wilson(ganhos, len(fechadas))[0] if fechadas else None, "pnl": sum(l["pnl"] or 0 for l in fechadas), "latencia_media_s": sum(l["latencia_s"] for l in linhas) / len(linhas)})
        return sorted(saida, key=lambda l: (l["tipo"], -l["pnl"]))

    def gravar_contexto(self, id_: str, ativo: str, tipo: str, valor: dict, origem: str, criado_em: pd.Timestamp, valido_ate: pd.Timestamp) -> None:
        self.con.execute("INSERT OR REPLACE INTO contexto VALUES (?, ?, ?, ?, ?, ?, ?)", (id_, ativo, tipo, json.dumps(valor, ensure_ascii=False), origem, criado_em.isoformat(), valido_ate.isoformat()))
        self.con.commit()

    def contexto_lido(self, id_: str) -> bool:
        return self.con.execute("SELECT 1 FROM contexto WHERE id = ?", (id_,)).fetchone() is not None

    def contexto_vigente(self, ativos: tuple[str, ...], agora: pd.Timestamp) -> tuple[dict, ...]:
        """Nada do futuro e nada vencido. A consulta é local e imediata: o motor nunca espera a LLM."""
        if not ativos:
            return ()
        marcas = ",".join("?" * len(ativos))
        linhas = self.con.execute(f"SELECT * FROM contexto WHERE ativo IN ({marcas}) AND criado_em <= ? AND valido_ate > ? ORDER BY criado_em DESC LIMIT 20", (*ativos, agora.isoformat(), agora.isoformat())).fetchall()
        return tuple({"ativo": l["ativo"], "tipo": l["tipo"], "valor": json.loads(l["valor"]), "origem": l["origem"], "criado_em": l["criado_em"], "valido_ate": l["valido_ate"]} for l in linhas)

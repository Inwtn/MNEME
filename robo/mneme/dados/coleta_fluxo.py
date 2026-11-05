"""Coleta contínua de trades, livro, derivativos e liquidações, com limites para nunca encher o disco nem a memória."""

from __future__ import annotations

import asyncio
import logging
import shutil
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import websockets

from .armazem import agora_utc
from .binance_fluxo import FonteFluxo, ler_mensagem, liquidacao_do_stream, livro_do_stream, trade_do_stream, url_futuros, url_spot
from .eventos import ArmazemEventos

log = logging.getLogger("mneme.fluxo")

SEM_MENSAGEM = 90  # só para o spot, que nunca fica calado; liquidações podem levar minutos
MAX_EM_MEMORIA = 200_000  # eventos por par e tipo à espera de gravação
MAX_PAGINAS_RECUPERACAO = 30
RETENCAO_DIAS = {"livro": 30, "trades": 365}


class ColetorFluxo:
    def __init__(self, pares: list[str], armazem: ArmazemEventos, fonte: FonteFluxo | None = None,
                 relogio: Callable[[], datetime] = agora_utc, descarga_segundos: int = 120, consulta_segundos: int = 60,
                 uso_disco: Callable[[], float] | None = None, limite_livro_pct: float = 85, limite_trades_pct: float = 92):
        self.pares, self.armazem, self.fonte, self.relogio = pares, armazem, fonte or FonteFluxo(), relogio
        self.descarga_segundos, self.consulta_segundos = descarga_segundos, consulta_segundos
        self.uso_disco = uso_disco or self._uso_real
        self.limite_livro_pct, self.limite_trades_pct = limite_livro_pct, limite_trades_pct
        self.buffers: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self.ultimo_trade: dict[str, int] = {}
        self.descartados: dict[str, int] = defaultdict(int)
        self.batimento = armazem.raiz / "fluxo.batimento"
        self._ultimo_batimento: datetime | None = None
        self._dia_manutencao: str | None = None
        self._recuperacoes: list[asyncio.Task] = []
        for par in pares:
            ultimo = armazem.ultimo("trades", par, "agg_id")
            if ultimo is not None:
                self.ultimo_trade[par] = int(ultimo)

    def _uso_real(self) -> float:
        self.armazem.raiz.mkdir(parents=True, exist_ok=True)
        uso = shutil.disk_usage(self.armazem.raiz)
        return uso.used / uso.total * 100

    def _guardar(self, tipo: str, par: str, linha: dict) -> None:
        fila = self.buffers[(tipo, par)]
        if len(fila) >= MAX_EM_MEMORIA:
            self.descartados[tipo] += 1
            return
        fila.append(linha)

    def receber_spot(self, mensagem: str | bytes) -> None:
        lida = ler_mensagem(mensagem)
        agora = self.relogio()
        self._bater(agora)
        if lida is None:
            return
        stream, dados = lida
        try:
            if stream.endswith("@aggTrade"):
                par, trade = trade_do_stream(dados, agora)
                self._guardar("trades", par, trade)
                self.ultimo_trade[par] = max(self.ultimo_trade.get(par, 0), trade["agg_id"])
            elif "@depth" in stream:
                par, livro = livro_do_stream(stream.split("@")[0].upper(), dados, agora)
                self._guardar("livro", par, livro)
        except (KeyError, TypeError, ValueError) as erro:
            log.warning("Mensagem ignorada em %s: %s", stream, erro.__class__.__name__)

    def receber_futuros(self, mensagem: str | bytes) -> None:
        lida = ler_mensagem(mensagem)
        if lida is None:
            return
        try:
            par, liquidacao = liquidacao_do_stream(lida[1], self.relogio())
            self._guardar("liquidacoes", par, liquidacao)
        except (KeyError, TypeError, ValueError) as erro:
            log.warning("Liquidação ignorada: %s", erro.__class__.__name__)

    def _bater(self, agora: datetime) -> None:
        if self._ultimo_batimento is None or agora - self._ultimo_batimento >= timedelta(seconds=10):
            self.batimento.parent.mkdir(parents=True, exist_ok=True)
            self.batimento.write_text(agora.isoformat(), encoding="utf-8")
            self._ultimo_batimento = agora

    def descarregar(self) -> int:
        """Grava o que está em memória, respeitando os limites de disco. Se a gravação falhar, os eventos ficam para a próxima."""
        uso = self.uso_disco()
        bloqueados = set()
        if uso >= self.limite_livro_pct:
            bloqueados.add("livro")
        if uso >= self.limite_trades_pct:
            bloqueados.add("trades")
        gravados = 0
        for (tipo, par), fila in list(self.buffers.items()):
            if not fila:
                continue
            if tipo in bloqueados:
                self.descartados[tipo] += len(fila)
                fila.clear()
                log.error("Disco em %.0f%%: descartando %s de %s.", uso, tipo, par)
                continue
            lote = list(fila)
            try:
                gravados += self.armazem.gravar(tipo, par, lote)
            except OSError as erro:
                log.error("Não gravei %s de %s (%s): %s eventos seguem em memória.", tipo, par, erro, len(lote))
                continue
            del fila[:len(lote)]
        return gravados

    def _preparar_recuperacao(self) -> Callable[[], int]:
        """Guarda onde a coleta parou antes de ler o stream novo; o REST cobre do ponto guardado até depois da conexão."""
        ponto = dict(self.ultimo_trade)
        return lambda: self.recuperar_trades(ponto)

    def recuperar_trades(self, ponto: dict[str, int] | None = None) -> int:
        """Busca por REST os trades perdidos numa queda. O livro não tem recuperação: a lacuna fica registrada pelo tempo."""
        total = 0
        agora = self.relogio()
        origem = self.ultimo_trade if ponto is None else ponto
        for par in self.pares:
            proximo = origem.get(par)
            if proximo is None:
                continue
            for _ in range(MAX_PAGINAS_RECUPERACAO):
                try:
                    pagina = self.fonte.trades_desde(par, proximo + 1, agora)
                except httpx.HTTPError as erro:
                    log.warning("Não recuperei trades de %s: %s", par, erro.__class__.__name__)
                    break
                if not pagina:
                    break
                for trade in pagina:
                    self._guardar("trades", par, trade)
                proximo = pagina[-1]["agg_id"]
                total += len(pagina)
                if len(pagina) < 1000:
                    break
            else:
                log.error("Recuperação de %s parou no limite de páginas: há lacuna de trades.", par)
            self.ultimo_trade[par] = max(self.ultimo_trade.get(par, 0), proximo)
        return total

    def consultar_derivativos(self) -> int:
        lidos = 0
        agora = self.relogio()
        for par in self.pares:
            try:
                self._guardar("derivativos", par, self.fonte.derivativos(par, agora))
                lidos += 1
            except (httpx.HTTPError, KeyError, ValueError) as erro:
                log.warning("Sem derivativos de %s: %s", par, erro.__class__.__name__)
        return lidos

    def manutencao(self) -> None:
        """Uma vez por dia: compacta os dias fechados e apaga o que passou da retenção."""
        agora = self.relogio()
        dia = f"{agora:%Y-%m-%d}"
        if dia == self._dia_manutencao:
            return
        self._dia_manutencao = dia
        compactados = self.armazem.compactar(agora)
        apagados = sum(self.armazem.limpar(tipo, dias, agora) for tipo, dias in RETENCAO_DIAS.items())
        log.info("Manutenção: %d dias compactados, %d apagados.", compactados, apagados)

    async def _laco_ws(self, nome: str, conectar: Callable, receber: Callable, parar: asyncio.Event, ao_conectar: Callable | None = None,
                       sem_mensagem: float | None = None, espera_inicial: float = 1) -> None:
        espera = espera_inicial
        while not parar.is_set():
            try:
                # Primeiro a conexão, depois o REST: assim não sobra janela sem nenhum dos dois.
                ponto = ao_conectar() if ao_conectar is not None else None
                async with conectar() as conexao:
                    log.info("%s conectado.", nome)
                    espera = espera_inicial
                    if ponto is not None:
                        self._recuperacoes.append(asyncio.create_task(asyncio.to_thread(ponto)))
                    iterador = aiter(conexao)
                    while not parar.is_set():
                        receber(await asyncio.wait_for(anext(iterador), sem_mensagem))
            except asyncio.CancelledError:
                raise
            except PermissionError as erro:
                log.error("%s sem permissão para gravar (%s).", nome, erro)
            except (OSError, TimeoutError, StopAsyncIteration, websockets.WebSocketException) as erro:
                log.warning("%s caiu (%s); nova tentativa em %.0f s.", nome, erro.__class__.__name__, espera)
            if not parar.is_set():
                await asyncio.sleep(espera)
                espera = min(max(espera, 0.01) * 2, 60)

    async def _periodico(self, segundos: float, tarefa: Callable, parar: asyncio.Event) -> None:
        while not parar.is_set():
            try:
                await asyncio.wait_for(parar.wait(), segundos)
            except TimeoutError:
                pass
            if parar.is_set():
                return
            try:
                await asyncio.to_thread(tarefa)
            except OSError as erro:
                log.error("Tarefa periódica falhou: %s", erro)

    async def rodar(self, parar: asyncio.Event | None = None, conectar_spot: Callable | None = None,
                    conectar_futuros: Callable | None = None, espera_inicial: float = 1) -> None:
        parar = parar or asyncio.Event()
        conectar_spot = conectar_spot or (lambda: websockets.connect(url_spot(self.pares), ping_interval=60, ping_timeout=30, max_queue=4096))
        conectar_futuros = conectar_futuros or (lambda: websockets.connect(url_futuros(self.pares), ping_interval=60, ping_timeout=30))
        await asyncio.to_thread(self.manutencao)
        tarefas = [
            asyncio.create_task(self._laco_ws("Spot", conectar_spot, self.receber_spot, parar, self._preparar_recuperacao, SEM_MENSAGEM, espera_inicial)),
            asyncio.create_task(self._laco_ws("Futuros", conectar_futuros, self.receber_futuros, parar, None, None, espera_inicial)),
            asyncio.create_task(self._periodico(self.descarga_segundos, self.descarregar, parar)),
            asyncio.create_task(self._periodico(self.consulta_segundos, self.consultar_derivativos, parar)),
            asyncio.create_task(self._periodico(3600, self.manutencao, parar)),
        ]
        await parar.wait()
        for tarefa in tarefas:
            tarefa.cancel()
        await asyncio.gather(*tarefas, return_exceptions=True)
        await asyncio.gather(*self._recuperacoes, return_exceptions=True)
        # Ao desligar, nada do que está em memória se perde.
        await asyncio.to_thread(self.descarregar)
        log.info("Coleta de fluxo encerrada; descartados: %s", dict(self.descartados))


def importar_derivativos(armazem: ArmazemEventos, pares: list[str], meses: int, fonte: FonteFluxo | None = None,
                         agora: datetime | None = None) -> dict[str, int]:
    """Funding de vários meses e o open interest que a Binance ainda guarda."""
    fonte = fonte or FonteFluxo()
    agora = agora or agora_utc()
    total = {"funding": 0, "open_interest": 0}
    for par in pares:
        total["funding"] += armazem.gravar("funding", par, fonte.funding_historico(par, agora - timedelta(days=meses * 31), agora))
        total["open_interest"] += armazem.gravar("open_interest", par, fonte.open_interest_historico(par, agora - timedelta(days=29), agora))
    armazem.compactar(agora)
    return total


def caminho_batimento(raiz: Path | str) -> Path:
    return Path(raiz) / "fluxo" / "fluxo.batimento"

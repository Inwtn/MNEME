# Robô MNEME (Python)

O robô que aprende com o mercado e opera **no simulado** antes de qualquer dinheiro real. A visão completa está no `AGENTS.md`.

## O que ele faz hoje

A cada minuto:

1. Lê as operações recentes dos traders no provedor de sinais.
2. Mede a taxa de acerto de **todo** trader pelas operações que ele encerra (30 dias), esteja ou não no ranking.
3. **Estratégia "seguir traders"** em Solana: compra quando a maioria dos traders de alto acerto compra o mesmo token e vende quando a maioria dos que formaram a entrada vende.
4. Respeita a meta e o limite do dia (meia-noite de Brasília).
5. Grava tudo no banco local `robo/dados/mneme.db` (carteira simulada de US$ 200.000, com 0,1% de taxa e 0,5% de slippage em cada ponta).

Os parâmetros vêm da tela de **Configurações** do site (`/api/training/settings`). Sem eles, o robô só observa.

## Como rodar no Mac

Precisa do `uv` (gerenciador de Python). Na pasta `robo/`:

```bash
uv sync
uv run pytest -q
bash rodar.sh
```

O `rodar.sh` mantém o Mac acordado enquanto o robô roda (Ctrl+C para parar). O endereço e a chave do provedor de sinais vêm do `.env` da raiz (`SIGNALS_REST_URL`, `SIGNALS_API_KEY`).

## Organização

| Arquivo | Para quê |
|---|---|
| `mneme/sinais.py` | Cliente do provedor de sinais |
| `mneme/conectores/solana.py` | Preço e liquidez de tokens de Solana |
| `mneme/acerto.py` | Mede o acerto de cada trader |
| `mneme/estrategias/seguir_traders.py` | Regra de entrada e saída |
| `mneme/carteira.py` | Carteira simulada, meta e limite do dia |
| `mneme/ciclo.py` | Um ciclo completo do robô |
| `mneme/banco.py` | Esquema do banco (SQLite agora, Postgres no servidor) |

## Estudo de velas (aprendizado de máquina)

```bash
uv run python -m mneme.estudo --dias 30 --horizonte 1 5 15
```

Baixa o histórico de velas de 1 minuto da Binance e mede se modelos conseguem prever a direção do preço nos próximos minutos, sempre em dados que o modelo nunca viu (walk-forward). Compara com o empate de uma aposta de direção (payout de 85% → 54,05% de acerto).

**Resultado em 31/10/2026** (BTC, ETH e SOL, 30 dias, só velas): os modelos acertaram de 50% a 53%, inclusive nos 20% de previsões mais confiantes. Nenhum passou dos 54,05%. Só com velas, não há sinal de direção que pague a aposta; o próximo estudo precisa de mais informação (fluxo dos traders, livro de ofertas, notícias).

## Base de conhecimento e setups

`conhecimento/` guarda o que foi pesquisado na web (conceitos, setups e estudos, com as fontes). Esses são os documentos do RAG. Cada setup vira uma regra em `mneme/setups/` e é medido em todo o histórico:

```bash
uv run python -m mneme.setups
```

O resultado de cada setup fica em `conhecimento/setups.md`. Em 31/10/2026, só **Bollinger + RSI em 15 minutos** passou do empate de 54,05%, em anos e moedas diferentes, com folga pequena.

### Teste ao vivo

Desde 31/10/2026, a cada ciclo o robô procura o sinal de Bollinger + RSI nas velas recém-fechadas de BTC, ETH e SOL, grava em `sinais_ao_vivo` e confere o resultado 15 minutos depois (`mneme/ao_vivo.py`). Nada vai para o Telegram. Placar:

```bash
uv run python -m mneme.ao_vivo
```

O setup só vira dica depois de algumas semanas acima do empate.

## Dados de mercado e leitura

`mneme/dados/` coleta velas de 1 minuto da Binance em Parquet, um arquivo por par e por dia, em `dados/mercado/`. O histórico vem dos arquivos públicos; o ao vivo vem do WebSocket; qualquer queda é recuperada por REST. Cada vela guarda a hora em que chegou, para `ArmazemVelas.ler(como_de=...)` devolver só o que já se sabia naquele instante. Vela incoerente vai para `dados/mercado/quarentena/`.

`mneme/indicadores.py` calcula médias, RSI, MACD, Bollinger, ATR, ADX, OBV, VWAP e delta de volume, conferidos com o TA-Lib nos testes. `mneme/leitura.py` monta, vela a vela, os atributos para modelos e backtest: tendência, estrutura de topos e fundos, suporte e resistência, rompimentos, consolidação e padrões. Nada olha o futuro, e um teste garante isso.

```bash
uv run python -m mneme.dados importar --meses 24
uv run python -m mneme.dados resumo
uv run python -m mneme.dados ler BTCUSDT --tempo 15min
uv run python -m mneme.dados coletar
```

Na Oracle A1, a coleta roda em Docker Compose, com limite de memória e reinício automático. Não usa chaves:

```bash
docker compose up -d --build
```

### Fluxo e derivativos

`mneme/dados/coleta_fluxo.py` coleta trades, livro de ofertas (20 níveis, uma foto por segundo), funding, open interest e liquidações em `dados/mercado/fluxo/`, em um serviço separado das velas. Numa queda, os trades são recuperados por REST; o livro não tem recuperação, e a lacuna fica visível. Dias fechados são compactados; o livro fica 30 dias e os trades, 365. Com o disco em 85%, o livro para de ser gravado; em 92%, os trades também. `mneme/fluxo.py` agrega tudo por minuto para modelos e backtest.

```bash
uv run python -m mneme.dados fluxo
uv run python -m mneme.dados importar-derivativos --meses 24
uv run python -m mneme.dados resumo-fluxo
```

## Próximos passos

A ordem de implementação está em `docs/architecture/ROADMAP.md`.

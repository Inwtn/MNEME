# O robô MNEME

Este documento descreve a estratégia de seguir traders em Solana, uma das estratégias do produto. A definição do MNEME está em [PRODUCT_CHARTER.md](PRODUCT_CHARTER.md).

## O que ele faz

Esta estratégia roda sozinha na nuvem, em código legado (Cloudflare Worker `mneme-telegram-bot`, código em `workers/bot/`) a cada minuto. Ela faz **daytrade em Solana seguindo a maioria dos traders de alta taxa de acerto**, estejam ou não no ranking:

1. **Lê o provedor de sinais**: as operações recentes de todos os traders, a cada minuto. O ranking dos 50 primeiros é consultado no máximo a cada 30 minutos (tabela `paper_training_ranking`) e só informa a posição de quem está no Top.
2. **Mede a taxa de acerto de cada trader**: acompanha cada compra de qualquer trader que aparece nas operações, esteja ou não no ranking, e, quando ele vende, registra se a operação fechou com lucro pelo preço de mercado. A taxa é o percentual de operações com lucro nos últimos 30 dias. O valor de cada operação não pesa: conta quem tem a amostra mínima e a taxa mínima de Configurações. O acerto é medido em qualquer rede, mas o robô só compra tokens de Solana.
3. **Entra quando a maioria de alto acerto compra**: dentro da janela de tempo configurada, os traders de alto acerto que estão comprando o mesmo token precisam somar o mínimo configurado e ser maioria sobre os de alto acerto que estão vendendo. Vale a última operação de cada trader na janela.
4. **Sai quando a maioria deles vende**: o robô guarda quem formou a entrada e vende quando mais da metade desses traders vender o token. Não existe alvo, stop ou tempo fixo por operação.
5. **Manda a dica no grupo do Telegram** a cada entrada (token, quantos traders de alto acerto, acerto médio, horário e variação em 24 h) e a cada saída (quantos dos traders da entrada venderam, horário e resultado da operação, já com taxa e slippage). As dicas não levam nomes de traders.
6. **Para de comprar no dia** ao atingir a meta de ganho ou o limite de perda definidos em Configurações. As vendas continuam. O dia vira à meia-noite de Brasília.

Hoje a execução é **simulada** (carteira paper `mneme-paper`, US$ 200.000, com 0,1% de taxa e 0,5% de slippage em cada ponta, ao preço real do mercado). A execução real em Solana é o próximo passo.

## Configurações

Tudo é editado no site, em **Configurações → Robô MNEME (nuvem)**, e lido pelo robô a cada minuto. Os campos começam vazios: **enquanto a regra não estiver preenchida, o robô só observa** e a página Treino Bot avisa "Regra incompleta".

| Campo | O que define |
|---|---|
| Taxa mínima de acerto do trader | Quem conta como "alto acerto" |
| Operações mínimas para medir o acerto | Amostra mínima; abaixo disso o trader não conta |
| Traders de alto acerto comprando juntos | Mínimo de compradores, que também precisam ser maioria |
| Janela de tempo | Quantos minutos para trás o robô olha |
| Tamanho de cada compra | % da carteira por entrada |
| Liquidez mínima do token | Opcional; em branco não filtra |
| Parar de comprar ao ganhar no dia | Meta do dia, em % do patrimônio na abertura do dia |
| Parar de comprar ao perder no dia | Limite do dia, em % do patrimônio na abertura do dia |

Os valores ficam na tabela `paper_training_settings` (D1 `mneme-operational`) e passam pela rota `GET/PUT /api/training/settings` do Pages.

## Onde ver

- **Treino Bot** (`/treino`): carteira, posições, movimentações, resultado do dia contra a meta e cada decisão do robô com o motivo ("maioria de alto acerto comprando", "aguardando", "meta atingida").
- **Traders medidos** (na mesma página): quantos traders já têm acerto medido nos últimos 30 dias, quantos têm a amostra mínima, quantos passam na taxa de Configurações e quanto tempo, em média, eles ficam em cada operação.
- **Grupo do Telegram**: as dicas de entrada e saída. O acesso ao grupo é pago (Mercado Pago, `/assinar`, `/acesso`).

## Dados (D1)

| Tabela | Para quê |
|---|---|
| `paper_training_signal_events` | Operações recentes dos traders (7 dias) |
| `paper_training_trader_positions` / `paper_training_trader_results` | Compras e vendas de cada trader, para medir o acerto e o tempo na operação (90 dias) |
| `paper_training_positions` | Posições abertas do robô, com os traders que formaram a entrada |
| `paper_training_orders` | Compras e vendas do robô |
| `paper_training_daily_metrics` | Patrimônio e resultado por dia de Brasília (a coluna se chama `day_utc` por histórico) |
| `paper_training_pattern_observations` | Decisões e motivos (30 dias) |
| `bot_group_signal_receipts` | Fila das dicas do grupo, com entrega única e retentativa |

## Limitações conhecidas

- O robô roda uma vez por minuto: uma entrada ou saída pode acontecer até cerca de um minuto depois dos traders.
- Se o provedor de sinais não responder num minuto, o robô não faz entradas nesse minuto. As saídas continuam: ele marca o preço das posições abertas e vende se a maioria dos traders da entrada já tiver vendido nas operações gravadas antes. Vendas que acontecerem durante a falha só são vistas quando o provedor voltar.
- O provedor de sinais cobra créditos por chamada. Sem créditos, ele responde HTTP 402 e o robô fica sem operações novas até a recarga (o robô ainda confere saídas). O robô faz uma chamada de operações por minuto e uma de ranking a cada 30 minutos.
- O robô consulta o preço de no máximo 30 tokens por minuto, com as posições abertas e os tokens de Solana primeiro. Uma compra de trader cujo token ficou sem preço não entra na medição do acerto.
- A taxa de acerto só existe depois que os traders encerram operações; nos primeiros dias, poucos traders terão amostra suficiente.
- O tempo na operação conta da compra do trader até o minuto em que o robô viu a venda. Operações encerradas antes da migração `0018` não têm esse tempo.
- As carteiras antigas (Conservador e Arriscado) continuam no banco, mas não operam mais.

## Fora deste robô

- O **bot local** em `src/` (Node e Docker) é legado e será aposentado depois que a execução real for levada para o robô.
- A **consulta de tokens** no Telegram (`/buscar` e afins) continua como está e será substituída no futuro por uma IA generativa.

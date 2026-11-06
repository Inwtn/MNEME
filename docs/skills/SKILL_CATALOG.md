# Catálogo de skills do MNEME

Biblioteca enxuta para o agente de desenvolvimento e pesquisa. Skills não fazem parte da arquitetura operacional e não redefinem o produto, que está no [Product Charter](../PRODUCT_CHARTER.md).

## Instaladas

| Skill | Quando usar | Origem | Scripts |
|---|---|---|---|
| `mneme-verificacao` | Antes de dizer que terminou, de fazer commit ou de entregar | Reescrita a partir de `obra/superpowers` | Nenhum |
| `mneme-auditoria-backtest` | Ao criar, revisar ou relatar backtest, modelo ou estratégia | Reescrita a partir de `agiprolabs/claude-trading-skills` e de ideias públicas | Nenhum |
| `mneme-revisao-injecao` | Ao ligar fonte externa, LLM, MCP ou skill externa | Reescrita a partir de `basitalisandhu/agent-security-skills` | Nenhum |

Ficam em `.claude/skills/`. As skills `frontend-design` e `power` já existiam, tratam só de design visual e continuam fora do Git.

## Fila de avaliação

Nada aqui está instalado. O motivo e a ordem estão no [plano de integração](SKILL_INTEGRATION_PLAN.md).

| Candidata | Repositório | Ajudaria em | Lote |
|---|---|---|---|
| `doubt-driven-development` | `addyosmani/agent-skills` | Questionar decisões de arquitetura | 2 |
| `observability-and-instrumentation` | `addyosmani/agent-skills` | Monitorar o motor em operação | 2 |
| `backtest-expert` | `tradermonty/claude-trading-skills` | Testes de estresse e método de robustez | 2 |
| `edge-candidate-agent` | `tradermonty/claude-trading-skills` | Ciclo de hipóteses, seção 8 do Charter | 2 |
| `pine-backtester` | `JerryLiu369/awesome-quant-skills` (agregador) | Scripts do TradingView | 2 |
| `market-microstructure`, `slippage-modeling` | `agiprolabs/claude-trading-skills` | Order flow e custos | 3 |
| `helius-api`, `whale-tracking`, `wallet-profiling` | `agiprolabs/claude-trading-skills` | Solana, on-chain e carteiras | 3 |
| `regime-detection` | `agiprolabs/claude-trading-skills` | Regimes na decisão | 3 |
| `supply-chain-risk-auditor` | `trailofbits/skills` | Auditar dependências | 3 |
| Graphify, só no modo local | `Graphify-Labs/graphify` | Reduzir o gasto de contexto | Experimento isolado |

A avaliação completa, inclusive do que foi recusado, está em [SKILL_EVALUATION.md](SKILL_EVALUATION.md).

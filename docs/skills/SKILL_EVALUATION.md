# Avaliação de skills open source

Feita em 06/11/2026. Números vieram da API do GitHub nesse dia. Nenhum script de terceiros foi executado, e nenhum plugin foi instalado.

## O que foi lido de verdade

| Nível | Significado |
|---|---|
| **Integral** | SKILL.md lido do começo ao fim, ou quase |
| **Parcial** | Início, seções ou busca por padrões de risco |
| **Lista** | Só nome, tamanho e estrutura de arquivos |

O agregador `sickn33` tem 9.016 SKILL.md, e `j4flmao` tem 645. Eles não foram avaliados um a um. Tudo o que não aparece abaixo fica como **Não utilizar**, até passar pelo processo do plano.

## Repositórios

| Repositório | Autor e tipo | ★ / forks | Último push | Licença | Skills | Testes | Classificação |
|---|---|---:|---|---|---:|---|---|
| [obra/superpowers](https://github.com/obra/superpowers) | Jesse Vincent, autor original | 313.502 / 27.892 | 03/11/2026 | MIT | 15 | Sim | **Adaptar** 1 skill. Não instalar o plugin |
| [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) | Addy Osmani, autor original | 113.694 / 11.885 | 01/11/2026 | MIT | 25 | Poucos | **Estudar** |
| [agiprolabs/claude-trading-skills](https://github.com/agiprolabs/claude-trading-skills) | agiprolabs, conta pessoal | 513 / 105 | 03/09/2026 | MIT | 68 | Quase nenhum | **Adaptar** 1 skill. Outras para estudo |
| [basitalisandhu/agent-security-skills](https://github.com/basitalisandhu/agent-security-skills) | Muhammad Basit Ali, autor original | 0 / 5 | 01/11/2026 | MIT | 10 | Sim | **Adaptar** 1 skill, só o método |
| [tradermonty/claude-trading-skills](https://github.com/tradermonty/claude-trading-skills) (achado na busca) | tradermonty, conta pessoal | 3.666 / 801 | 06/11/2026 | MIT | Várias | Sim, por skill | **Estudar** |
| [trailofbits/skills](https://github.com/trailofbits/skills) (achado na busca) | Trail of Bits, empresa de segurança | 8.045 / 683 | 06/11/2026 | CC-BY-SA-4.0 | Várias | Parcial | **Estudar** |
| [anthropics/skills](https://github.com/anthropics/skills) (achado na busca) | Anthropic | 188.108 / 22.189 | 28/10/2026 | Varia por skill | 18 | Não avaliado | **Não utilizar**: as úteis já existem neste ambiente |
| [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) | Graphify Labs, empresa | 143.435 / 13.720 | 06/11/2026 | Apache-2.0 | 0 | Sim | **Estudar**, em experimento isolado |
| [Jakeschincariol/day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) | Jake Schincariol | 5.741 / 1.416 | 20/10/2026 | MIT | 11 | Sim | **Estudar**: a ideia de reproduzir sessões |
| [JerryLiu369/awesome-quant-skills](https://github.com/JerryLiu369/awesome-quant-skills) | **Agregador** | 2 / 3 | 03/11/2026 | MIT, com ressalva | 33 | Não | **Estudar**, indo sempre ao autor original |
| [LLMQuant/awesome-trading-agents](https://github.com/LLMQuant/awesome-trading-agents) | **Lista de links** | 983 / 168 | 13/08/2026 | CC0-1.0 | 0 | Não | **Estudar** como índice |
| [sickn33/agentic-awesome-skills](https://github.com/sickn33/agentic-awesome-skills) | **Agregador** | 49.276 / 7.151 | 06/11/2026 | MIT, com ressalva | 9.016 | Parcial | **Não utilizar**: serve para achar autores |
| [j4flmao/agent-skills](https://github.com/j4flmao/agent-skills) | Coleção de uma pessoa | 39 / 5 | 03/11/2026 | MIT | 645 | Não | **Não utilizar** |
| [wshobson/agents](https://github.com/wshobson/agents) (achado na busca) | wshobson | 42.259 / 4.464 | 05/11/2026 | MIT | Várias | Não avaliado | **Não utilizar**: a de backtest é rasa |
| [shakeebshaan/claude-code-quant-skills](https://github.com/shakeebshaan/claude-code-quant-skills) (achado na busca) | shakeebshaan | 2 / 1 | 17/04/2026 | MIT | Não avaliado | Não avaliado | **Não utilizar**: sem adoção nem manutenção |

## Skills analisadas

| Skill | Origem | Leitura | Classificação | Por quê |
|---|---|---|---|---|
| `verification-before-completion` | obra | Integral | **Adaptar** | Ataca o erro real da `carteira.py`. Curta, sem scripts. Reescrita com a suíte, os serviços e o fluxo do MNEME |
| `using-superpowers` | obra | Parcial | **Não utilizar** | Exige invocar skills antes de qualquer resposta e carrega por gancho no início da sessão. Disputa com o Charter e com as instruções do dono |
| `systematic-debugging`, `test-driven-development` | obra | Lista | **Estudar** | Parecem úteis, mas custam contexto. Só entram se uma falha real justificar |
| `walk-forward-validation` | agiprolabs | Parcial | **Adaptar** | Boa explicação de purga, embargo, DSR e PBO. O laboratório já implementa isso, então o valor está em exigir o uso |
| `risk-management` | agiprolabs | Parcial | **Estudar** | O Risk Engine já é código determinístico. Uma skill não deve competir com ele |
| `dex-execution` | agiprolabs | Parcial | **Não utilizar** | Lê `WALLET_PRIVATE_KEY` do ambiente, assina e envia swap em mainnet. Fere o simulado primeiro. Serve de leitura quando chegar a etapa de Jupiter |
| `market-microstructure`, `slippage-modeling`, `regime-detection`, `whale-tracking`, `trade-journal` | agiprolabs | Lista e início | **Estudar** | Ligadas a lacunas do Charter. Ainda precisam de leitura integral |
| `backtesting-bias-avoidance` | quantskills, trazida por JerryLiu369 | Parcial | **Estudar** | O repositório original traz texto de licença GNU, enquanto o agregador é MIT. Nenhum texto foi copiado. Tem ★0, então não há adoção comprovada |
| `backtest-review`, `data-quality-audit`, `stats-test-picker` | JerryLiu369 (agregador) | Lista | **Estudar** | É preciso achar o autor original antes de qualquer uso |
| `pine-backtester` | JerryLiu369 (agregador) | Lista | **Estudar** | Pode ajudar nos scripts do TradingView. Lote 2 |
| `prompt-injection-review` | basitalisandhu | Parcial | **Adaptar** | Método claro de origem e aprovação. O repositório tem pouca adoção, por isso aproveitei só a ideia e deixei os scripts de fora, embora o inventário só use biblioteca padrão |
| `mcp-server-review`, `tool-approval-gate-audit` | basitalisandhu | Lista | **Estudar** | Úteis quando o MNEME tiver MCP ou ferramentas com efeito real |
| `context-engineering` | addyosmani | Parcial | **Estudar** | Boa, mas o Charter e a memória já cobrem o ponto principal, e ela custa cerca de 2.200 palavras |
| `observability-and-instrumentation` | addyosmani | Parcial | **Estudar** | Candidata para quando o motor tiver mais operações |
| `backtest-expert` | tradermonty | Parcial | **Estudar** | Boa filosofia: procurar o que quebra menos. Foco em ações, script com testes ainda não lido |
| `edge-candidate-agent` | tradermonty | Lista | **Estudar** | Pode inspirar o ciclo de hipóteses |
| `supply-chain-risk-auditor` | trailofbits | Parcial | **Estudar** | Autor forte e método sério. A licença exige compartilhar adaptações nos mesmos termos, e os scripts ainda precisam de inspeção |
| `backtesting-frameworks` | wshobson | Parcial | **Não utilizar** | Cerca de 310 palavras genéricas. O laboratório já vai além |
| `prompt-injection-defense` | BagelHole, trazida por sickn33 | Parcial | **Não utilizar** | Sobrepõe a revisão adotada. O agregador informa a origem, o que é bom |
| `ml/time-series` | j4flmao | Parcial | **Não utilizar** | Texto genérico de previsão. Um lote de 645 skills de uma pessoa tem risco de qualidade e de contexto |
| `trader-broker`, `trader-pelosi`, `trader-timemachine` e outras | Jakeschincariol | Lista e README | **Não utilizar**, e estudar `timemachine` | Foco em ações dos EUA, com Yahoo e SEC. A ideia de reproduzir a sessão muitas vezes pode inspirar um experimento |
| Graphify | Graphify Labs | Parcial | **Estudar** | O modo local por AST parece útil, mas documentos usam LLM, e o projeto tem oferta paga na nuvem. Exige dependência nova |

## O que a avaliação mostrou

- **Estrelas não bastam.** O `day-trader-skill` tem 17 dias, 1 commit e 5.741 estrelas. Isso pode ser só a audiência do autor, que tem 3.468 seguidores. Não encontrei prova de manipulação, mas popularidade também não prova qualidade.
- **Agregador não é autor.** O crédito e a licença precisam vir do repositório original.
- **Licença de agregador pode divergir da original.** O caso de `backtesting-bias-avoidance` mostra isso.
- **O MNEME já tem o principal de backtest.** Walk-forward, purga, embargo, Holm, PBO, Sharpe deflacionado e placebo já existem. Um motor de backtest de terceiros seria duplicação.
- **Skills de trading podem conflitar com o Charter.** Algumas assinam transações reais ou têm foco só em ações.

## Limites

Esta avaliação não comprova que as skills melhoram o trabalho do agente. Isso só se mede com o uso. A qualidade foi julgada por leitura, e as estrelas podem mudar. As buscas na web também citaram registros de terceiros, que não usei como fonte de contagem.

## Fontes

- API do GitHub, consultada em 06/11/2026, nos repositórios citados.
- [shakeebshaan/claude-code-quant-skills](https://github.com/shakeebshaan/claude-code-quant-skills), [tradermonty, backtest-expert](https://claudemarketplaces.com/skills/tradermonty/claude-trading-skills/backtest-expert) e [wshobson, backtesting-frameworks](https://claudemarketplaces.com/skills/wshobson/agents/backtesting-frameworks), achados na busca.
- [Trail of Bits, repositório de skills](https://osrepos.com/repo/trailofbits-skills), achado na busca.

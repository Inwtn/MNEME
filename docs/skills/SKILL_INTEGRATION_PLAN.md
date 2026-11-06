# Plano de integração de skills

Skills ampliam o agente de desenvolvimento e pesquisa. Elas não substituem a arquitetura operacional do MNEME e não redefinem o [Product Charter](../PRODUCT_CHARTER.md). Este trabalho não interrompe o desenvolvimento do robô.

## Regras

A intenção é aproveitar o que a comunidade já fez. Popularidade não é prova, mas uma preocupação vaga também não é motivo para recusar.

**Instale a original** quando a licença permitir e ela for útil para o Charter.

**Só estas situações bloqueiam a instalação:**

1. Gancho ou plugin que roda sozinho e não foi aprovado pelo dono.
2. Pedido de chave privada, assinatura de transação ou envio de ordem real.
3. Instrução que tente passar por cima do Charter ou do Risk Engine.
4. Código com comportamento suspeito ou não inspecionado.
5. Licença que não permita o uso no repositório.

## Como instalar

1. Ache o autor original, e não o agregador.
2. Baixe como dado, sem executar. Leia o SKILL.md e procure rede, chaves e subprocessos nos scripts.
3. Copie a pasta para `.claude/skills/`, com `LICENSE` e `ORIGEM.txt`, e libere o nome no `.gitignore`.
4. Adicione ao [catálogo](SKILL_CATALOG.md) e à lista de `robo/tests/test_skills.py`.
5. Rode a suíte completa, seguindo `mneme-verificacao`, e faça um commit separado.

Scripts de terceiros usam API pública com chave opcional, e essa chave fica só no `.env`. Antes de um script virar parte do robô, ele precisa de teste próprio.

## Lotes

| Lote | Estado | Skills |
|---|---|---|
| **1** | Instalado | 11 originais e 3 feitas para o MNEME, listadas no catálogo |
| **2** | Na próxima etapa de hipóteses e TradingView | `edge-candidate-agent`, `pine-backtester`, `feature-engineering`, `risk-management` |
| **3** | Na etapa de Solana e segurança | `helius-api`, `wallet-profiling`, `prompt-injection-review`, `mcp-server-review`, `supply-chain-risk-auditor` |
| **Experimento** | Se o gasto de contexto incomodar | Graphify, no modo local |

## Plugin superpowers

As skills `systematic-debugging` e `test-driven-development` já estão instaladas. O plugin completo adiciona um gancho no início de cada sessão e faz a skill `using-superpowers` ser usada antes de qualquer resposta. A decisão de instalar é do dono, com `/plugin` em um terminal do Claude Code. Com ele, o Charter continua valendo.

## Como medir e remover

- A cada lote, veja se a skill foi usada e se ajudou. Skill sem uso sai.
- Para remover, apague a pasta, a linha do catálogo e a entrada de `robo/tests/test_skills.py`. O histórico fica no Git.

## O que os testes cobrem

`robo/tests/test_skills.py` confere formato, licença, origem, ausência de ganchos e presença no catálogo. Nas skills `mneme-*`, confere também a referência ao Charter e as frases proibidas.

Esses testes não provam que a skill é ativada no momento certo. Isso só se confirma numa sessão nova.

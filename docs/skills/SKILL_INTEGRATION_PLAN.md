# Plano de integração de skills

Skills ampliam o agente de desenvolvimento e pesquisa. Elas não substituem a arquitetura operacional do MNEME e não redefinem o [Product Charter](../PRODUCT_CHARTER.md). Este trabalho não interrompe o desenvolvimento do robô.

## Regras

1. **Reescrever, em vez de copiar.** A skill entra adaptada ao código do MNEME, curta e em português, com crédito ao autor original.
2. **Sem plugins nem ganchos de terceiros.** Nada roda sozinho ao iniciar a sessão.
3. **Sem scripts no primeiro momento.** Um script só entra depois de lido por inteiro, testado no ambiente do projeto e com a dependência justificada.
4. **O Charter manda.** A skill não muda objetivo, mercados, regras de risco nem autoriza operação.
5. **Sem chave nem dinheiro.** Skill que peça chave privada, assine transação ou envie ordem fica fora.
6. **Licença do autor original.** Só se reutiliza texto se a licença permitir e for compatível com o repositório.
7. **Limite de tamanho.** Até 100 linhas por skill e descrição de até 300 caracteres, para gastar pouco contexto.
8. **Skill precisa de um motivo real.** Ela responde a uma falha ou a uma lacuna do Charter.

## Lote 1: incorporado

| Skill | Falha ou lacuna que resolve |
|---|---|
| `mneme-verificacao` | Sobrescrita da `carteira.py` e commits incompletos |
| `mneme-auditoria-backtest` | Exposição da área selada e resultados sem correção |
| `mneme-revisao-injecao` | Fontes externas entrando, e LLM com baixa resistência a ataques |

## Próximos lotes

| Lote | Quando | O que avaliar |
|---|---|---|
| **2** | Quando o motor estiver acumulando operações e o ciclo de hipóteses começar | `backtest-expert`, `edge-candidate-agent`, `observability-and-instrumentation`, `doubt-driven-development`, `pine-backtester` |
| **3** | Quando chegar a etapa de Solana, on-chain e order flow | `market-microstructure`, `slippage-modeling`, `helius-api`, `whale-tracking`, `wallet-profiling`, `regime-detection`, `supply-chain-risk-auditor` |
| **Experimento** | Se o gasto de contexto virar problema medido | Graphify no modo local, em uma cópia isolada, comparando o gasto com e sem ele |

## Como incorporar uma skill

1. Ache o autor original, e não o agregador.
2. Registre em [SKILL_EVALUATION.md](SKILL_EVALUATION.md): licença, manutenção, testes e nível de leitura.
3. Leia o SKILL.md e os scripts como dados. Não execute nada para descobrir o que faz.
4. Rode a revisão de `mneme-revisao-injecao`.
5. Escreva a versão do MNEME em `.claude/skills/mneme-<nome>/`.
6. Adicione ao [catálogo](SKILL_CATALOG.md).
7. Rode `robo/tests/test_skills.py` e a suíte completa, seguindo `mneme-verificacao`.
8. Faça um commit separado.

## Como medir e remover

- A cada lote, veja se a skill foi usada e se evitou algum erro. Skill sem uso sai.
- Para remover, apague a pasta e a linha do catálogo. O histórico fica no Git.

## O que os testes cobrem

`robo/tests/test_skills.py` confere o formato, o tamanho, a ausência de scripts e ganchos, a referência ao Charter, a presença no catálogo e frases proibidas, como autorizar operação real.

Esses testes não provam que a skill é ativada no momento certo. Isso só se confirma numa sessão nova.

# ADR-0015: Operar Forex, ouro e expiração fixa

**Situação:** aceita pelo dono em 06/11/2026. Substitui a parte da [ADR-0008](0008-matriz-por-mercado.md) que deixava a Quotex só com sinal.

**Contexto:** o MNEME é um robô de operações multi-mercado. O dono definiu que ele também opera Forex, ouro e operações de expiração fixa estilo Quotex.

**Decisão:** um motor único, com um adaptador por modalidade. Todos os mercados começam no simulado. A execução real de cada um só é ligada com resultado medido, Risk Engine aprovando e integração autorizada pelo dono.

**Consequências:**

- O simulado funciona hoje com preço de referência e payout e custos declarados como hipótese até serem medidos.
- A execução real na Quotex continua sem caminho: nenhuma API oficial foi encontrada. Abrir esse caminho exige uma nova decisão do dono, com os termos da corretora conferidos.
- Forex e ouro ao vivo dependem de uma fonte de preço em tempo real. Sem ela, o Risk Engine recusa por dado velho.

**Alternativa recusada:** três robôs separados, um por mercado.

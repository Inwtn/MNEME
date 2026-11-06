# ADR-0008: Matriz de capacidade por mercado

**Situação:** proposta.

**Contexto:** o sistema cobre Binance, Solana, forex e opções digitais. Não foi encontrada API oficial da Quotex, e a automação sem API oficial está excluída.

**Decisão:**

| Mercado | Dados | Sinal | Execução |
|---|---|---|---|
| Solana | Sim | Sim | Depois da promoção |
| Binance Spot | Sim | Sim | Depois da promoção |
| Binance Futuros | Só leitura | Não | Bloqueada |
| Forex e opções digitais | Em fonte de referência | Sim | Não |

Cada célula é imposta em código. Cada mercado tem modelos, custos, métricas e limites próprios.

**Atualização:** a [ADR-0015](0015-operar-forex-ouro-e-expiracao-fixa.md) passou a operação simulada de Forex, ouro e expiração fixa para o escopo.

**Consequências originais, substituídas pela ADR-0015:** o robô não opera na Quotex, salvo se surgir uma API oficial, o que exigirá novo ADR. Os sinais são medidos em fonte de referência, não na plataforma.

**Alternativa recusada:** automação de navegador ou endpoints privados, excluída pelo próprio pedido e com risco de bloqueio da conta.

# ADR-0002: Núcleo determinístico, LLM nas bordas

**Situação:** proposta.

**Contexto:** o pedido quer um sistema capaz de interpretar notícias, sem ser "um chatbot fantasiado de trader". A visão proíbe o LLM de decidir compras sozinho. Decisões por LLM não são reproduzíveis nem medidas com facilidade, e a evidência fora da amostra é fraca.

**Decisão:** o LLM é a camada de estudo: interpreta, pesquisa, formula hipóteses, analisa operações e propõe melhorias, como define o [Product Charter](../../PRODUCT_CHARTER.md). Direção, tamanho e execução em tempo real vêm de modelos e regras medidos, e uma proposta só entra depois de validada.

**Consequências:** o sistema continua funcionando sem LLM, e uma notícia só influencia operação depois de testada. O limite é que eventos raros, sem amostra, geram aviso em vez de operação.

**Alternativa recusada:** agente LLM decidindo a ordem.

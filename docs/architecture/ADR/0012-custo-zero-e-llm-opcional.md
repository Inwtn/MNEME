# ADR-0012: Custo zero com LLM local sob demanda

**Situação:** proposta. Revisada em 05/11/2026 por pedido do dono, que trocou a API paga por modelo local.

**Contexto:** o orçamento é R$ 0, e a conta Oracle agora pode gerar cobrança se sair do limite grátis. A máquina não tem GPU, e um LLM local disputa os mesmos 2 OCPU com a coleta.

**Decisão:** Ollama com modelo Qwen pequeno e quantizado, escolhido por medição, atrás de uma porta. Ele roda só por evento, é descarregado depois do uso e nunca bloqueia coleta nem sinais. Embeddings ficam locais. API paga é opcional e nunca requisito, exigindo aprovação e teto.

**Consequências:** nenhum custo por token. Em troca, há latência alta e qualidade menor, o que hoje limita o papel previsto no Charter. O modelo local começa por extração e resumo estruturados; o raciocínio longo, como pesquisa e análise de operações, roda em lote, e o que for crítico em tempo não depende dele.

**Alternativa recusada:** API paga como dependência; LLM rodando em toda vela.

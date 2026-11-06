# Stack tecnológica

**Situação:** referência de arquitetura, subordinada ao [Product Charter](../PRODUCT_CHARTER.md). O estado real está em [RASTREABILIDADE.md](RASTREABILIDADE.md). Licenças e suporte a ARM foram lidos do PyPI e do apt da A1 em 05/11/2026.

## Restrição que define tudo

A máquina é uma A1 com **2 OCPU, 12 GB e 142 GB livres**, e a regra é custo zero. Dos 200 GB grátis de disco restam 3 GB para novos volumes. Por isso, cada serviço a mais precisa justificar a memória que usa.

## Decisão por item

| Item | Decisão | Quando | Justificativa | Alternativa |
|---|---|---|---|---|
| Python 3.12+ | **Adotar** | Já usado | É a regra da visão; a A1 tem 3.12.3 | Nenhuma |
| `uv` | **Manter** | Já usado | Funcionou na A1 | pip |
| Pydantic | **Adotar** | Fase 1 | Valida contratos e dados externos | dataclasses |
| httpx | **Manter** | Já usado | Cliente atual | Nenhuma |
| pandas, NumPy, scikit-learn | **Manter** | Já usados | Base do estudo atual | Nenhuma |
| PostgreSQL 16 | **Adotar** | Fase 1 | Vários processos e o vetor no mesmo banco; está no apt ARM (16.15) | Continuar em SQLite |
| pgvector | **Adotar** | Fase 4 | Sem segundo serviço; adequado abaixo de milhões de vetores. O apt traz 0.6.0; `halfvec` exige versão mais nova | Qdrant |
| Qdrant | **Não agora** | Se precisar | Um serviço a mais para um volume que o Postgres atende. Reavaliar se o índice crescer muito | pgvector |
| TimescaleDB, ClickHouse | **Não agora** | Se medir gargalo | Parquet + DuckDB atende à pesquisa com muito menos memória. ClickHouse é pesado para 12 GB | Parquet + DuckDB |
| Parquet + DuckDB | **Adotar** | Fase 1 | Dado de mercado barato, em arquivo, fácil de versionar; há binário ARM | Timescale |
| Redis Streams, Kafka | **Não adotar** | Se medir gargalo | Um único processo de ingestão não precisa de corretor; Kafka é excessivo aqui | Tabela `outbox` no Postgres e `asyncio` |
| LangGraph | **Adotar** | Fase 7 | Estado, checkpoints e retomada; `langgraph` e `langgraph-checkpoint-postgres` são MIT | Código próprio |
| LangChain | **Não adotar** | - | O LangGraph não exige o framework LangChain; menos camadas para manter | Chamada direta à API |
| LlamaIndex | **Não adotar** | Reavaliar na fase 4 | O pipeline pedido é curto e precisa de metadados próprios | Código próprio |
| `fastembed` | **Adotar** | Fase 4 | Embeddings em CPU, locais e sem custo; Apache-2.0 | API paga |
| Ollama + Qwen pequeno | **Adotar** | Fase 4 | Sem custo por token; carrega e descarrega sob demanda. Modelo e limites vêm da medição em [ORACLE_ALWAYS_FREE_DEPLOYMENT](ORACLE_ALWAYS_FREE_DEPLOYMENT.md) | `llama.cpp` direto; sem LLM |
| LLM pago por API | **Nunca obrigatório** | Só com aprovação | Fica atrás da mesma porta, como opção para o que o modelo local não fizer bem | Modelo local |
| LightGBM, XGBoost | **Adotar primeiro** | Fase 6 | Rápidos em CPU, fortes em dados tabulares; há binário ARM. Competem medidos | Regressão logística |
| CatBoost | **Só para comparar** | Fase 6 | Apache, com ARM; sem dependência em produção antes de superar os dois primeiros | Nenhuma |
| PyTorch | **Só em pesquisa** | Fase 10 | Pesado; usar CPU na A1 só para inferência, com treino fora | Sem deep learning |
| Stable-Baselines3 | **Só em pesquisa** | Fase 10 | MIT; depende de um simulador confiável, que vem antes | Regras de tamanho fixas |
| FinRL | **Não adotar como base** | Fase 10, como referência | O próprio projeto indica outro repositório para produção; manutenção incerta | Stable-Baselines3 |
| vectorbt | **Só pesquisa interna** | Reavaliar na fase 2 | Licença com Commons Clause, a validar. Backtest próprio é necessário para custos por mercado | Backtest próprio |
| TA-Lib | **Opcional** | Fase 2 | Binário ARM incluso. Usar se as fórmulas próprias não bastarem, conferindo licença | Fórmulas próprias com testes |
| MLflow | **Mínimo** | Fase 6 | `mlflow-skinny` em arquivo local, sem servidor sempre ligado. Conferir a licença declarada | Tabela própria |
| FastAPI | **Só se necessário** | Fase 8 | Hoje o robô não recebe conexões, e isso é mais seguro. Enviar resumos para o site atende ao painel | Sem API |
| Docker Compose | **Adotar** | Fase 0 | Pedido do dono: limites de memória e CPU por serviço, implantação repetível. Sem Kubernetes | `systemd` puro |
| Monitor de recursos | **Adotar leve** | Fase 0 | Script próprio com aviso no Telegram, com vigia externo na Micro | Prometheus |
| Prometheus, Grafana | **Adiar** | Depois da fase 8 | Cabem na A1, mas gastam memória que hoje serve à coleta | Monitor leve |
| Next.js | **Não adotar** | - | O site em HTML/JS no Pages funciona. Trocar seria migração sem necessidade | Site atual |

## Stack final proposta

```text
Linguagem   Python 3.12, uv, Pydantic, httpx, asyncio
Dados       PostgreSQL 16 + pgvector; Parquet + DuckDB
ML          scikit-learn, LightGBM, XGBoost; mlflow-skinny em arquivo
LLM         LangGraph + Ollama com Qwen pequeno, sob demanda
Embeddings  fastembed (CPU, local)
Operação    Docker Compose, log estruturado, Telegram, backup diário
Site        Cloudflare Pages + D1 (como hoje)
```

## Custos operacionais

| Item | Custo |
|---|---|
| Oracle A1, Postgres, Parquet, modelos locais | Zero, dentro do Always Free; conferir o relatório de custo da Oracle |
| Binance, BCB, GDELT, RSS | Zero; respeitar os limites de uso |
| Agendas oficiais (Fed, BEA, BCB, IBGE, ECB, Eurostat) | Zero |
| FRED | **Fora dos dados de treino:** os termos proíbem uso para treinar ML. Ver [ADR-0014](ADR/0014-calendario-economico.md) |
| Jupiter | Grátis até 1 requisição por segundo com chave |
| Provedor de sinais | **Já é pago**, por crédito |
| LLM local | Zero em dinheiro; gasta CPU e memória |
| LLM pago | Opcional; requer aprovação e teto mensal |
| Helius ou similares | Plano grátis; pago só com aprovação |

## Fontes

- [Comparativo pgvector e Qdrant](https://encore.dev/resources/pgvector-vs-qdrant)
- [Edições do TimescaleDB](https://www.tigerdata.com/docs/about/latest/timescaledb-editions)
- [Termos do vectorbt](https://vectorbt.dev/terms)
- [FinRL README](https://cdn.jsdelivr.net/gh/AI4Finance-Foundation/FinRL@master/README.md)
- [TA-Lib no PyPI](https://pypi.org/project/ta-lib)
- [Limites do Jupiter](https://developers.jup.ag/docs/portal/faq)
- [Termos do FRED](https://fred.stlouisfed.org/legal/terms/)

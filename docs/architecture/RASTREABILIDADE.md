# Matriz de rastreabilidade

Estado real em 05/11/2026, verificado na máquina e no código. Código existente não conta como funcionalidade: uma capacidade só está completa quando seus dados são coletados, guardados, processados e chegam a quem precisa deles.

**Validada** quer dizer que o componente funciona. Não quer dizer que dá lucro.

## Dados e fontes

| Capacidade | Implementada | Rodando | Alimenta o modelo | Validada | Pendente |
|---|---|---|---:|---|---|
| Velas de 1 min (BTC, ETH, SOL), 24 meses | Sim | Sim, ao vivo | **Sim** | Sim: sem lacunas, recuperação testada | Mais ativos |
| Agressão vinda das velas | Sim | Sim | **Sim** | Sim | |
| Funding | Sim | Sim | **Sim** | Parcial | Atualização nos modelos, ao retreinar |
| Trades | Sim | Sim, desde 05/11 | **Não** | Sim: bate com a vela oficial | Atributos, depois de acumular histórico |
| Livro de ofertas | Sim | Sim, desde 05/11 | **Não** | Parcial | Atributos, depois de acumular histórico |
| Open interest | Sim | Sim; histórico de 29 dias | **Não** | Parcial | Atributos |
| Liquidações | Sim | Conectado, sem evento recebido | **Não** | **Não** | Confirmar com evento real |
| Calendário: FOMC | Sim | Sim, 57 reuniões | **Sim** | Sim: datas e fuso conferidos | |
| Calendário: agenda e previsões da semana | Sim | Sim | **Não** | Parcial | Valor divulgado, surpresa e histórico |
| Notícias (10 fontes por RSS) | Sim | Sim, desde 05/11 | **Não** | Parcial: fluxo testado, classificação sem amostra rotulada | Atributos; classificação medida |
| X (API oficial) | Sim, com teto de gasto | **Não: sem credencial** | **Não** | Só com dados simulados | Credencial e orçamento; tendências |
| Provedor de sinais (traders) | Sim | Só no Mac | **Não** | Parcial | Migrar o robô |
| Forex (EUR/USD) | **Não** | Não | **Não** | Não | Fonte, dataset e modelos |
| Solana on-chain | **Não** | Não | **Não** | Não | Fonte e dataset |

## Conhecimento

| Capacidade | Implementada | Consultada por alguém | Validada | Pendente |
|---|---|---|---|---|
| Biblioteca de metodologias | Sim, um arquivo | **Não** | Referências sem conferência | Ingestão |
| Estudos e setups (`robo/conhecimento/`) | Sim | **Não** | Medidos pelo laboratório | Ingestão |
| RAG, embeddings e busca | **Não** | Não | Não | Tudo |
| Fontes externas de conhecimento | **Não** | Não | Acesso testado: arXiv e ChartSchool abertos; Investopedia e SSRN bloqueados | Pipeline de aquisição |
| LLM local e LangGraph | **Não**, só medição | Não | Qualidade baixa em amostra pequena | Integração |

## Técnicas

| Capacidade | Calculada | Chega ao modelo | Acrescenta previsão? |
|---|---|---|---|
| RSI, MACD, Bollinger, ATR, ADX, VWAP, médias | Sim, conferidas com TA-Lib | Sim | É a base "só preço" |
| Estrutura, suporte e resistência, rompimentos, padrões de vela | Sim | Sim | Dentro da base |
| Fibonacci, FVG, Order Block, Ichimoku, linhas de tendência, perfil de volume, varredura, spring, topo e fundo duplos | Sim | Sim | **Não, na medição em conjunto** |
| Combinações específicas entre técnicas | Só por interação no modelo | Sim | **Ainda não medido uma a uma** |
| Harmônicos, Volume Spread, ombro-cabeça-ombro, triângulos, divergências | **Não** | Não | Não medido |
| Elliott Wave | **Não**: subjetivo | Não | Não testável como está |

## Modelos

| Modelo | Treinado | Em uso | Tipo de resultado | Resultado |
|---|---|---|---|---|
| LightGBM de direção, 15 e 60 min, 3 pares | Sim | **Sim: previsor grava sem operar** | Fora da amostra | AUC de 0,517 a 0,543; abaixo do empate |
| XGBoost e regressão logística | Só nos estudos | Não | Fora da amostra | Equivalentes ao LightGBM |
| Volatilidade | Só nos estudos | Não | Fora da amostra | **R² de 0,46 a 0,72**, de 9% a 21% melhor que a referência |
| Eficiência do movimento (regime) | Só nos estudos | Não | Fora da amostra | Quase nada |
| Meta-rótulo sobre regras de reversão | Só nos estudos | Não | Fora da amostra | Nada significativo depois da correção |

## Fluxo de decisão

| Etapa | Situação |
|---|---|
| Dados, múltiplos tempos, indicadores, padrões | Funciona |
| Consultar metodologias | **Não existe** |
| Notícias e informações externas | Coleta funciona, mas **não chega à decisão** |
| Avaliar evidências com modelos | Funciona para velas, funding e FOMC |
| Decision Engine | **Não existe** |
| Risk Engine | **Não existe**; só limites do robô antigo |
| Signal Engine | **Não existe**; só dicas do robô antigo |
| Paper trading dos novos modelos | **Não existe**; o previsor só grava previsões |

## Origem dos resultados

| Tipo | O que existe |
|---|---|
| Backtest | 54 combinações de setups em opção digital e 54 em spot; nenhuma aprovada |
| Fora da amostra | Modelos com walk-forward, purga e embargo; corte de seleção só com o passado, depois da correção |
| Área selada (desde 01/08/2026) | **Nenhuma hipótese aberta**: nada mereceu o teste final. Estudos anteriores à criação da área tocaram esses meses |
| Ao vivo, sem operar | Previsões gravadas desde 05/11/2026; amostra ainda sem valor estatístico |
| Paper trading dos novos modelos | **Nenhum** |

## Medições que mudaram conclusões

- **Vazamento corrigido:** selecionar os 20% melhores usando todo o período inflava o resultado. Reversão em ETH, 15 min: de **58,53%** com o corte antigo para **54,30%** com o corte só do passado. Parte da queda também vem de usar menos dados, e nenhuma linha fica significativa.
- **Metodologias:** média entre os pares, 15 min, AUC de 0,5341 com metodologias e 0,5345 só com preço. Elas não acrescentaram previsão de direção nessa forma de uso.
- **Direção:** existe sinal acima do acaso, com AUC próximo de 0,53, mas abaixo do que o payout exige.
- **Volatilidade:** é o que os dados preveem melhor. Serve para filtrar momentos, dimensionar risco e escolher quando não operar.

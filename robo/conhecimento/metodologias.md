---
tipo: metodologias
atualizado_em: 2026-11-05
---

# Biblioteca de metodologias

Esta é a biblioteca única do MNEME sobre escolas de análise de mercado. O RAG consulta este arquivo para explicar conceitos, e o código em `mneme/indicadores.py`, `mneme/leitura.py` e `mneme/metodologias.py` calcula as regras.

**Nenhuma metodologia decide sozinha.** Cada uma vira uma evidência numérica no mesmo conjunto de dados (`mneme/laboratorio/dataset.py`). O modelo aprende quando cada evidência importa, e existe um só caminho de decisão.

**Evidência:**
- **Forte:** estudos revisados com efeito replicado.
- **Mista:** estudos divergentes, ou efeito que depende de mercado, período ou custos.
- **Fraca:** pouco estudo independente, ou resultados perto do acaso.
- **Sem validação:** popular, sem estudo acadêmico relevante encontrado.

Esta classificação resume a literatura citada e nossas medições. Ela é um ponto de partida, não um veredito sobre todo uso possível. As referências foram citadas de memória: confira a edição e os dados antes de citar em outro lugar.

## Indicadores e leitura de preço

| Metodologia | Regra no MNEME | Evidência | Limitações | Referências |
|---|---|---|---|---|
| RSI | Wilder, 14 períodos; conferido com TA-Lib | Mista | Sobrecompra pode durar toda uma tendência | Wilder (1978), *New Concepts in Technical Trading Systems* |
| ATR | Média de Wilder da amplitude real | Forte como medida de volatilidade; não prevê direção | Só mede tamanho do movimento | Wilder (1978) |
| ADX, DI+ e DI− | Wilder, 14 períodos | Mista | Atrasa, e não indica sentido sozinho | Wilder (1978) |
| MACD | 12, 26 e 9 | Mista | Atraso; muitos falsos cruzamentos em lateralidade | Appel, *Technical Analysis: Power Tools for Active Investors* |
| Bollinger | Média de 20 e 2 desvios | Mista | Toque na banda não é sinal por si | Bollinger (2001), *Bollinger on Bollinger Bands* |
| Médias móveis | EMA e SMA | Mista: favorável em dados antigos, enfraquece com custos e em períodos recentes | Atraso | Brock, Lakonishok e LeBaron (1992); Sullivan, Timmermann e White (1999) |
| VWAP | Do dia, reiniciada à 0h UTC | Forte como referência de execução; mista para previsão | O início da sessão muda o valor em cripto, que nunca fecha | Berkowitz, Logue e Noser (1988) |
| OBV | Soma do volume com sinal | Fraca | Sensível a uma única vela | Granville (1963) |
| Ichimoku | 9, 26 e 52; nuvem deslocada em 26 velas | Fraca | Parâmetros vêm de outro mercado e outra época | Hosoda; Elliott (2007), *Ichimoku Charts* |

## Price Action e padrões

| Metodologia | Regra no MNEME | Evidência | Limitações | Referências |
|---|---|---|---|---|
| Estrutura de mercado | Dois últimos topos e fundos confirmados | Sem validação como tal; relacionada ao momentum | O pivô só se confirma depois | Dow; Murphy (1999), *Technical Analysis of the Financial Markets* |
| Suporte e resistência | Últimos pivôs confirmados | Mista: há evidência de concentração de ordens em níveis | Muitas definições | Osler (2000), *Support for Resistance* |
| Rompimentos e falsos rompimentos | Fechamento além do nível anterior, com retorno em até 3 velas | Mista | Depende de custo e volatilidade | Medição interna em `setups.md` |
| Linhas de tendência | Reta pelos dois últimos pivôs | Sem validação | Traçado subjetivo na prática | Murphy (1999); Edwards e Magee |
| Fibonacci | Retração na última perna confirmada; zona de 50% a 78,6% e distância até 61,8% | Fraca | A escolha da perna muda tudo; a popularidade pode criar autorrealização | Literatura acadêmica escassa; a testar |
| Padrões de vela | Engolfo, martelo, estrela e doji | Fraca: sozinhos, quase aleatórios em 1 minuto | Muitas formas e nenhuma regra única | Nison (1991); Marshall, Young e Rose (2006); medição interna |
| Padrões gráficos | Topo e fundo duplos, por dois pivôs a menos de 0,5 ATR | Mista | Reconhecimento subjetivo | Lo, Mamaysky e Wang (2000); Bulkowski; Chang e Osler (1999) |
| Harmônicos | **Ainda não implementado** | Sem validação | Relações exatas com tolerâncias arbitrárias | Carney, *Harmonic Trading* |
| Elliott Wave | **Não testável como está** | Sem validação | A contagem é subjetiva e costuma ser refeita depois do fato | Frost e Prechter, *Elliott Wave Principle* |

## Volume, fluxo e posicionamento

| Metodologia | Regra no MNEME | Evidência | Limitações | Referências |
|---|---|---|---|---|
| Delta e agressão | Volume comprador menos vendedor | Forte no curtíssimo prazo | Efeito de segundos a minutos; pode não superar custos | Cont, Kukanov e Stoikov (2014) |
| Livro de ofertas | Desequilíbrio em 5 e 20 níveis, spread e profundidade | Forte no curtíssimo prazo | Ordens podem ser canceladas | Cont, Kukanov e Stoikov (2014); O'Hara (1995) |
| Perfil de volume | POC e área de valor em 96 velas | Sem validação | Janela arbitrária | Steidlmayer (Market Profile) |
| Funding e open interest | Valor, variação e desvio | Mista | Histórico curto de open interest; só 29 dias em nossa base | A levantar |
| Wyckoff | Spring: varredura de nível logo após consolidação | Sem validação | Formalização parcial da escola | Wyckoff; Weis |

## Smart Money e ICT

Essas escolas vêm da prática de traders, sobretudo Michael Huddleston (ICT), sem definição oficial única nem estudos revisados relevantes encontrados. As regras abaixo são a nossa interpretação.

| Metodologia | Regra no MNEME | Evidência | Limitações |
|---|---|---|---|
| Fair Value Gap | Lacuna de 3 velas até fechamento além dela | Sem validação | Parente de gaps clássicos; pequenos gaps abundam |
| Order Block | Última vela contrária antes de um rompimento | Sem validação | Várias definições; muito viés ao olhar o passado |
| Varredura de liquidez | Fura o nível e fecha de volta | Sem validação | Parente do falso rompimento |

## Como cada mercado usa isso

A escolha não é fixa em uma lista por escola: cada mercado tem modelos e medições próprios, e o modelo daquele mercado aprende o que serve nele.

| Mercado | Evidências que entram | Avaliação |
|---|---|---|
| **Binance** | Preço, metodologias, fluxo, derivativos e notícias | Retorno líquido de taxa e slippage |
| **Solana** | Tudo acima que for aplicável, mais liquidez, carteiras, holders e risco do token | Retorno líquido, com perda total contada |
| **Quotex** | Preço, tendência, níveis, padrões, volatilidade, notícias, calendário e macro, conforme o prazo de expiração | Acerto contra o empate do payout |

Dados exclusivos de cripto, como funding, nunca entram em forex.

## O que medimos até agora

Os resultados saem de `mneme.laboratorio` e ficam em [`setups.md`](setups.md). Uma metodologia só muda de "sem validação" aqui se a medição, depois de custos e correção, mostrar que ela acrescenta algo. Se não acrescentar, ela segue disponível para consulta, mas não recebe peso.

## Literatura geral

- Park e Irwin (2007), *What Do We Know About the Profitability of Technical Analysis?*
- Lo, Mamaysky e Wang (2000), *Foundations of Technical Analysis*.
- Hsu, Taylor e Wang (2016), *Technical trading: Is it still beating the foreign exchange market?*
- López de Prado (2018), *Advances in Financial Machine Learning*.
- Estudos sobre cripto em curto prazo: [`estudos.md`](estudos.md).

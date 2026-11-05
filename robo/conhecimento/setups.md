---
tipo: setups
pesquisado_em: 2026-10-31
testado_em: 2026-11-05
dados: velas de 1 min da Binance, BTC/ETH/SOL, nov/2024 a nov/2026
empate: 54,05% (aposta de direção com payout de 85%)
---

# Setups encontrados e o resultado de cada um

Cada setup tem a regra exata em `mneme/setups/__init__.py` e é medido por `uv run python -m mneme.laboratorio setups`.

**Método:** entrada na abertura da vela seguinte ao sinal, uma aposta por vez, empates fora. Um setup só passa se o p-valor, ajustado por 54 combinações (Holm), ficar abaixo de 0,05, e se o acerto superar o empate nas duas metades do período e com 1 minuto de atraso.

**Controles do motor:** placebo com direção sorteada em 50,00%; nenhum setup olhando o futuro; passeio aleatório sem vencedor.

## Resultado: nenhum setup passou

Faixa de acerto entre os três pares:

| Setup | De onde veio | 5 min | 15 min | Pares acima de 50%, com correção | Veredito |
|---|---|---:|---:|---:|---|
| **Reversão após movimento forte de 1 h** | Estudo acadêmico de Bitcoin (2021) | 52,88–53,78% | **54,20–54,54%** | 6 de 6 | Vantagem real sobre 50%; não comprovada sobre o empate |
| **Bollinger + RSI** | Scripts de scalping (reversão à média) | 53,44–54,79% | 53,19–54,65% | 6 de 6 | Vantagem real sobre 50%; não comprovada sobre o empate |
| RSI 4 saindo de 80/20 | Guias de scalping | 51,48–51,83% | 51,53–52,03% | 6 de 6 | Pequena; não paga |
| Rejeição em suporte/resistência | Guias de opção binária | 50,78–51,06% | 50,99–51,81% | 1 de 6 | Não paga |
| Martelo / estrela cadente sozinhos | Cursos de padrões de vela | 50,36–50,78% | 49,96–50,22% | 2 de 6 | Quase aleatório |
| Rejeição em S/R a favor da EMA 10 | Guias de opção binária | 49,53–50,54% | 50,23–50,45% | 0 de 6 | Aleatório |
| Engolfo sozinho | Cursos de padrões de vela | 49,42–50,01% | 49,58–49,73% | 0 de 6 | Aleatório |
| Cruzamento EMA 9/21 + VWAP | Guias de scalping | 48,93–49,74% | 48,76–48,88% | 0 de 6 | Perde |
| Três velas da mesma cor (continua) | Sinal popular | 48,14–48,95% | 48,56–48,87% | 0 de 6 | Perde |

Cinco combinações ficaram acima do empate antes da correção (melhor: Bollinger + RSI, ETH, 5 min, 54,79%, 16.947 sinais, p = 0,027, p ajustado = 1,0). Essa folga cai dentro do que 54 tentativas produzem por acaso. O Sharpe deflacionado do melhor resultado foi 0,000. A PBO de 0,000 só mostra que a ordem entre os setups é estável, porque os ruins continuam ruins; ela não indica lucro.

## O que os números ensinam

1. **No curto prazo, cripto volta mais do que continua.** Isso se repete nos três pares: reversão acima de 50%, continuação abaixo.
2. **O payout decide tudo.** Combinações acima do empate: nenhuma com 80%, 5 com 85% e 12 com 90% (empate de 52,63%), antes de qualquer correção. Medir o payout real é o próximo dado mais valioso.
3. **Padrão de vela sozinho não prevê nada** em 1 minuto.
4. **A medição antiga era otimista.** Bollinger + RSI em 15 minutos aparecia como 54–56%, contando sinais sobrepostos e entrada no fechamento do sinal. Agora mede 53,19–54,65%.

## Spot: custos vencem

Só compra, com 0,10% de taxa e 0,02% de slippage por ponta, ou seja, 0,24% por operação completa. As 54 combinações perderam:

| Barreiras | Retorno médio por operação |
|---|---:|
| 2 ATR de 1 min, até 60 min | -0,232% a -0,254% |
| 15 ATR de 1 min, até 480 min | -0,164% a -0,271% |

O retorno médio fica perto do próprio custo. Nenhum destes setups serve para spot nesse horizonte.

## Modelos de velas (`mneme.laboratorio modelos`)

Validação walk-forward com embargo e uma amostra por horizonte, sem alvos sobrepostos:

| | 5 min | 15 min |
|---|---:|---:|
| Regressão logística | 51,23–52,13% | 51,56–52,39% |
| Gradient boosting | 51,27–51,85% | 51,17–52,30% |
| Rótulo embaralhado (controle) | 49,91–50,09% | 49,58–50,56% |

Nenhum modelo passou do empate. Nos 20% mais confiantes, a regressão logística em ETH, 5 min, chegou a 54,59% em 35.191 previsões (p = 0,023 sem correção). É a próxima hipótese a testar, não um resultado.

## Previsões confiantes (`mneme.laboratorio robustez`)

Atualiza o parágrafo acima. LightGBM, 20% mais confiantes com corte só do passado, até 31/07/2026. Empate de 54,05%. O intervalo sorteia dias inteiros.

| Par | Min | n | Acerto | Intervalo de 95% | p ajustado | Atraso de 1 min | Trimestres acima |
|---|---:|---:|---:|---|---:|---:|---:|
| ETH | 15 | 6.036 | 57,19% | 55,91–58,52% | < 0,0001 | 56,33% | 6/6 |
| ETH | 5 | 17.740 | 56,21% | 55,51–56,91% | < 0,0001 | 55,31% | 6/6 |
| BTC | 15 | 4.627 | 56,19% | 54,79–57,64% | 0,013 | 55,31% | 4/6 |
| BTC | 60 | 1.419 | 56,66% | 54,06–59,38% | 0,155 | 55,81% | 4/6 |
| SOL | 15 | 4.299 | 55,38% | 53,82–56,87% | 0,206 | 55,15% | 5/6 |
| ETH | 60 | 1.339 | 55,27% | 52,54–57,92% | 0,583 | 55,34% | 5/6 |
| BTC | 5 | 12.405 | 54,66% | 53,70–55,56% | 0,352 | 54,01% | 5/6 |
| SOL | 5 | 15.757 | 54,29% | 53,48–55,04% | 0,583 | 53,32% | 3/6 |
| SOL | 60 | 1.376 | 51,96% | 49,33–54,63% | 0,943 | 52,19% | 1/6 |

Controles em ETH, 15 min: esconder o futuro não muda nenhum atributo, e o rótulo embaralhado dá 48,88%. É candidato, não aprovação: a área selada não foi aberta, e o resultado depende do preço e do payout reais da corretora. Com payout de 75%, ETH 15 min fica no zero. Em 91% dos sinais o modelo aposta contra os últimos 15 minutos.

## Combinações de metodologias (`mneme.laboratorio combinacoes`)

Sete combinações, em 15 e 60 min de gráfico, com saída em 15 e 60 min. Cortes fixados antes de medir. Nenhuma das 84 medições passa do empate ou de 50% depois da correção, e 18 têm menos de 100 sinais. A melhor foi Fibonacci + suporte/resistência em BTC (54,04%, n = 644, limite inferior de 50,18%), sem significância. As combinações reduzem sinais sem ganho consistente sobre a melhor parte.

Partes isoladas: RSI extremo fica perto de 55% nos três pares (limite inferior de até 53,99%, abaixo do empate). Rompimento acerta só de 43% a 44%. Tudo aponta para reversão de curto prazo. Operar contra rompimentos é hipótese nova, a registrar antes de medir.

## Limites desta medição

- São só 24 meses, e os pares são correlacionados: Holm é conservador nesse caso.
- O preço é o da Binance, não o da corretora de apostas, e o payout é suposto.
- O acerto dos traders não foi refeito aqui: esses dados estão no robô do Mac.
- O teste ao vivo de Bollinger + RSI continua, sem enviar sinais.

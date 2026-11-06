---
name: mneme-auditoria-backtest
description: Use ao criar, revisar ou relatar backtest, estudo, modelo ou estratégia do MNEME. Audita vazamento de dados, sobreajuste, área selada, custos e amostra usando o laboratório do próprio projeto.
---

# Auditoria de backtest

O produto é definido em `docs/PRODUCT_CHARTER.md`. Use as ferramentas de `robo/mneme/laboratorio/` e não crie um motor de backtest paralelo.

## Antes de calcular

- **Área selada:** corte os dados em `SELADO_DESDE` antes de qualquer cálculo. Não ajuste nada olhando esse período.
- **Candle, previsão, entrada e expiração** são coisas separadas. Declare cada uma.
- **Nenhum dado do futuro:** todo atributo usa só o que já existia. Em dado coletado ao vivo, respeite a hora de chegada. Teste se cortar o futuro muda o passado.
- **Modalidade:** meça na modalidade em que vai operar. Expiração fixa usa payout e empate; stop e alvo usam custo e risco. Resultado de uma não vale para a outra.

## Validação

| Pergunta | Ferramenta |
|---|---|
| A divisão respeita o tempo, com purga e embargo? | `dobras_walk_forward` |
| O corte de confiança vem só do passado? | `selecionar_com_passado` |
| Dado embaralhado cai para cerca de 50%? | `placebo_direcao` e `estressar` |
| O acerto se sustenta entre dias? | `intervalo_por_dias` |
| Sobrevive a tantos testes feitos? | `holm` e a família testada inteira |
| A escolha da melhor estratégia foi sobreajuste? | `prob_sobreajuste` (PBO) e `sharpe_deflacionado` |
| Sobrevive com atraso e custos? | `medir_operacoes`, com atraso de pelo menos 1 minuto |

## Sinais de problema

- Vantagem alta em poucas operações, ou que some com 1 minuto de atraso.
- Hipótese ajustada depois de ver o resultado, ou contagem de testes por baixo.
- Resultado concentrado em um trimestre, ativo ou regime.
- Payout ou custo sem aviso de que é hipótese.
- Modelo que usa a mesma janela para treinar e escolher o corte.

## Como relatar

- Registre o experimento com `Registro.anotar`, inclusive se der negativo.
- Mostre amostra, intervalo, expectativa líquida, o que foi corrigido e o que não foi.
- Diga "sem vantagem medida, nestas condições", e não "a técnica não funciona" nem "aprovada".
- Nenhum candidato é aprovado sem as validações e a área selada.

## Crédito

Ideias públicas organizadas a partir de `walk-forward-validation` ([agiprolabs/claude-trading-skills](https://github.com/agiprolabs/claude-trading-skills), MIT), `backtesting-bias-avoidance` ([quantskills](https://github.com/quantskills/skill-backtesting-bias-avoidance), licença GPL, nenhum texto copiado) e dos trabalhos de Bailey e López de Prado. Reescrita para o MNEME.

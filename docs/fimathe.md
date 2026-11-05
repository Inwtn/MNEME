# Fimathe no catálogo comum do MNEME

A Fimathe foi integrada a `mneme.setups.SETUPS` e ao laboratório comum de estratégias, sem página própria. Treino Bot lista o mesmo catálogo gerado por `mneme.laboratorio.catalogo`: dez setups e dois modelos, com resultados medidos importados por ativo e período.

## Configuração e estudo

Defina os parâmetros em Configurações → Fimathe e exporte o JSON. Os campos começam vazios; sem configuração completa, a estratégia só observa. A regra só é aplicada ao símbolo declarado no JSON, para impedir o uso de contrato e custos do ouro em BTC/ETH/SOL.

Na pasta `robo`:

```sh
uv run python -m mneme.laboratorio catalogo
uv run python -m mneme.laboratorio --pares XAUUSD --config-estrategias dados/fimathe-config.json setups --minutos 5 15
uv run python -m mneme.laboratorio --pares XAUUSD --config-estrategias dados/fimathe-config.json spot
uv run python -m mneme.laboratorio fimathe --config dados/fimathe-config.json --csv dados/xauusd.csv --fonte "Exportação XAUUSD da corretora"
```

Os dois primeiros estudos usam as velas de 1 minuto do armazém comum. Para XAUUSD, é preciso importar/coletar dados verificáveis desse ativo; o conector Binance não fornece ouro/Forex. O último comando aceita CSV M1/M5/M15 e grava o resultado em `dados/laboratorio/fimathe.json`, anotando a tentativa em `experimentos.jsonl`, o mesmo registro usado pelos outros estudos. Resultados `setups.json`, `spot.json`, `modelos.json` e `fimathe.json` podem ser carregados na seção comum de Treino Bot. Não há sincronização automática com a nuvem.

## Modos comparáveis

- `setups`: avalia os sinais de direção da Fimathe pelos mesmos horizontes, placebos, detector de dados futuros e correção estatística dos demais setups. Essa medição de direção não é o PnL da estratégia com stop e alvo.
- `spot`: o adaptador preserva os stops e alvos do canal, spread, slippage, comissão, limite de exposição, lote pelo risco e limites diários da Fimathe. Não substitui essas regras por ATR. O retorno é calculado sobre o patrimônio anterior à entrada. A linha identifica `execucao=risco_configurado`; o benchmark dos outros setups permanece `spot_atr`. Compare as políticas de alocação e a modalidade, além do ativo/período.
- `fimathe`: replay do CSV no mesmo registro, com relatório completo e métricas de posições; não aplica nem anuncia aprovação estatística fora da amostra.

A formação do canal a partir do armazém usa somente grupos completos de velas de 1 minuto. Não preenche buracos nem usa o restante de uma vela ainda não fechada. Um cruzamento sem a vela anterior contígua não gera sinal, e uma entrada sem a próxima abertura contígua é descartada.

## Regra experimental e limites

Interpretação de canais trazida do laboratório local Aurum. A referência usa quatro velas por pavios/corpos; gatilhos ficam a uma amplitude acima/abaixo do canal, confirmados no fechamento. Entra na abertura seguinte, com stop no extremo oposto e alvo pelo risco; uma posição por vez. Após fechar, remarca pelas últimas N velas e não opera a própria vela da remarcação. Vela ambígua conta stop primeiro; gaps podem superar o risco planejado. Meta/limite diário bloqueiam novas entradas até meia-noite de Brasília, mantendo saídas.

O motor não replica toda a metodologia discricionária de Marcelo Ferreira, nem o emulador do TradingView. A posição que já existe na conta TradingView não foi migrada. CSV bid OHLC exige contrato/custos compatíveis com sua fonte. Horários sem zona usam o deslocamento UTC informado; arquivos que atravessam mudanças de fuso devem ser convertidos para ISO com zona ou Unix.

Configurações ficam por origem no navegador; exporte o JSON para o runner. Os testes usam preços sintéticos para verificar código, sem validar rentabilidade. Não há resultado fora da amostra, probabilidade presumida, execução real, swap, margem, liquidação por margem, execução parcial nem drawdown intrabar completo. A Fimathe não é habilitada automaticamente no ciclo ao vivo ou no Telegram.

## Verificação

Os testes cobrem o motor, confirmação de fechamento, ausência de dados futuros, formação dos períodos, lacunas, contrato do ativo correto, custos, integração com o runner/registro e correspondência entre catálogo Python e painel. `uv run pytest tests/test_fimathe.py tests/test_laboratorio.py -q`.

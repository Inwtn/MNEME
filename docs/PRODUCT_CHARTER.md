# Product Charter do MNEME

**Fonte única de verdade do produto, definida pelo dono em 06/11/2026.** Toda decisão futura parte daqui. Roadmaps e arquitetura definem prioridades e caminhos, mas não redefinem o produto. Se outro documento divergir, este vale, e o outro precisa ser corrigido. Só o dono do projeto altera este arquivo.

## 1. Definição

MNEME é uma inteligência artificial financeira híbrida, baseada em Machine Learning, Deep Learning, LLMs generativas, análise quantitativa, RAG e múltiplas fontes de dados, cujo objetivo é estudar os mercados financeiros, identificar oportunidades, prever movimentos e operar de forma inteligente em diferentes mercados e modalidades.

É um sistema de inteligência financeira com capacidade operacional. **O produto final é o robô funcionando.**

O MNEME não é:

- um chatbot financeiro;
- apenas um analisador de gráficos;
- somente um gerador de sinais;
- exclusivamente um robô de criptomoedas;
- vários robôs independentes sem uma inteligência compartilhada.

## 2. Mercados

Todos fazem parte do escopo central. Nenhum é ideia futura a ser redescoberta em cada sessão.

| Mercado | Inclui | Lógica operacional |
|---|---|---|
| **Forex e instrumentos relacionados** | EUR/USD, GBP/USD, USD/JPY, outros pares, XAU/USD (ouro) e outros instrumentos incorporados | Compra e venda no estilo de uma corretora como a Binance, com acompanhamento de preços e análise de mercado |
| **Criptomoedas** | Bitcoin, Ethereum, Solana e outros criptoativos; spot; futuros, quando aplicável; ecossistema Solana; Jupiter e DEXs; dados on-chain, liquidez, carteiras e grandes participantes | Mercado centralizado e descentralizado, com adaptadores apropriados |
| **Expiração fixa, estilo Quotex** | Os ativos disponíveis na modalidade | Prever CALL ou PUT, identificar a entrada, avaliar tempos de expiração, considerar o payout, calcular a probabilidade de equilíbrio e a expectativa matemática, registrar e acompanhar os resultados |

Expiração fixa não é Forex convencional nem futuros: cada modalidade tem a própria lógica.

**Ordem definida pelo dono para a Quotex:** primeiro sinais. Depois, se for possível, o robô opera por uma API ou controlando a tela, com os termos da corretora conferidos, o risco de bloqueio da conta medido, resultado comprovado e autorização do dono.

## 3. Uma inteligência central

A inteligência é uma só e usa os mesmos princípios de análise, conhecimento técnico, aprendizado e contextualização em todos os mercados. Módulos diferentes não são produtos independentes, e o cérebro não é duplicado por corretora.

Cada mercado pode ter adaptadores, dados, atributos, modelos, estratégias, regras de execução e controles de risco próprios. Uma estratégia lucrativa em um mercado não é considerada lucrativa em outro antes de ser medida nele.

## 4. Inteligência híbrida

**Machine Learning e Deep Learning** aprendem com dados históricos e operacionais, reconhecem padrões, estimam probabilidades, identificam regimes, preveem volatilidade e avaliam oportunidades. São avaliados continuamente, retreinados quando apropriado e comparados com as versões anteriores.

**A LLM generativa** não se reduz a classificar notícias ou gerar relatórios. Ela é uma camada de inteligência que:

- interpreta informações complexas;
- lê e estuda documentações e consulta o RAG;
- aprende técnicas e conceitos a partir de fontes confiáveis;
- interpreta acontecimentos econômicos e geopolíticos e os correlaciona com os mercados;
- investiga estratégias e formula hipóteses;
- analisa operações anteriores, identifica erros e limitações e propõe melhorias;
- ajuda a evoluir as estratégias e os modelos.

Ela contribui por um ciclo estruturado de pesquisa, experimentação e avaliação. Ela **não altera diretamente** parâmetros operacionais nem o Risk Engine.

**O RAG e o conhecimento técnico** cobrem Price Action, Market Structure, Fibonacci, Elliott Wave, Harmonic Patterns, Wyckoff, SMC/ICT, Order Blocks, Fair Value Gaps, Liquidity Sweeps, Volume Profile, Order Flow, indicadores, candlestick patterns, análise multi-timeframe e outras técnicas relevantes. Não é só uma lista em um documento: são conhecimentos consultáveis e ferramentas que podem ser usadas, combinadas, testadas e avaliadas estatisticamente.

## 5. O mercado por dentro e por fora

| Perspectiva | Fontes |
|---|---|
| **Interna** | Candles, gráficos, indicadores, linhas de tendência desenhadas e identificadas, suportes e resistências, padrões gráficos, order book, trades, volume, liquidez, open interest, funding, dados on-chain |
| **Externa** | Notícias, X/Twitter e Trending Topics, calendários econômicos, bancos centrais, indicadores macroeconômicos, decisões políticas, geopolítica, documentações técnicas, comunicados oficiais, pesquisas e estudos, informações sobre empresas, projetos e instituições |

A inteligência correlaciona as duas. Exemplo: no primeiro turno da eleição presidencial brasileira de 2026, um resultado pode alterar as expectativas sobre o dólar. O MNEME deve identificar o acontecimento, entender o contexto econômico, verificar a informação, identificar os ativos afetados e estudar o impacto nos preços.

## 6. Dois ritmos

| Ritmo | O que roda | Regra |
|---|---|---|
| **Tempo real** | Modelos quantitativos, ML, atributos, Decision Engine, Risk Engine e execução | Nunca espera a LLM |
| **Assíncrono** | LLM, RAG, notícias, verificação de fatos, pesquisa de técnicas, interpretação de eventos e explicações | O contexto é guardado com hora, validade e origem |

## 7. Operação de ponta a ponta

1. Monitorar os mercados.
2. Receber dados internos e externos.
3. Interpretar o contexto.
4. Consultar conhecimento técnico.
5. Identificar oportunidades.
6. Analisar diferentes cenários.
7. Estimar probabilidades.
8. Selecionar estratégias adequadas.
9. Calcular riscos e expectativa matemática.
10. Decidir se deve operar.
11. Definir entrada, direção, saída ou expiração.
12. Executar em paper trading ou por integração operacional autorizada.
13. Monitorar a operação.
14. Registrar os resultados.
15. Aprender com as experiências.
16. Melhorar as próximas decisões.

## 8. Evolução contínua como trader

1. Acompanhar os resultados das operações.
2. Identificar estratégias vencedoras e perdedoras.
3. Estudar os contextos em que cada estratégia funciona.
4. Pesquisar novas metodologias e técnicas.
5. Consultar documentações e estudos.
6. Formular novas hipóteses.
7. Criar experimentos.
8. Testar novos atributos e combinações.
9. Comparar modelos e estratégias.
10. Incorporar melhorias somente após validação.
11. Registrar o conhecimento adquirido.
12. Reavaliar periodicamente as estratégias existentes.

O MNEME não fica limitado ao conhecimento inicial dos seus arquivos. Aprender continuamente não é retreinar sem controle: toda evolução precisa ser mensurável, versionada, reproduzível e reversível.

## 9. Regras permanentes

- **Simulado primeiro, em todos os mercados.** Nada vai para dinheiro real sem resultado medido e autorização do dono.
- **Poucas operações não são evidência.** A área selada de validação fica protegida, nenhum candidato é aprovado sem as validações, e nenhum resultado negativo é escondido.
- **Risco fora da LLM.** O Risk Engine é código determinístico, e a LLM não envia ordens.
- **Sigilo.** A fonte de sinais não é identificada, e o repositório público não recebe chaves, IPs ou dados privados.
- **Custo zero**, até o dono pedir outra coisa.

## 10. Objetivo não é estado atual

Descrever uma capacidade aqui não quer dizer que ela existe. O que falta continua no escopo: "ainda não existe" nunca quer dizer "não faz parte do produto".

Estado verificado no código e no servidor em 06/11/2026. Funcionar não quer dizer dar lucro. Os detalhes ficam em [RASTREABILIDADE.md](architecture/RASTREABILIDADE.md).

| Capacidade | Estado |
|---|---|
| Velas, trades, livro, funding e open interest de BTC, ETH e SOL | **Funciona**, ao vivo |
| Calendário, resultados macro e notícias por RSS | **Funciona**, ao vivo |
| Laboratório com validação, área selada e registro de experimentos | **Funciona** |
| Motor único: decisão, risco, sinal, execução simulada, diário e apuração | **Funciona** em simulado, com testes de ponta a ponta. Pouca operação ao vivo até agora |
| Expiração fixa: CALL/PUT, payout, empate e expectativa | **Funciona** em simulado. Payout é hipótese. Sinal ainda não vai para o Telegram |
| Forex e ouro com stop e alvo | **Parcial**: histórico e medição prontos, resultado medido negativo. Sem fonte ao vivo no servidor e sem corretora |
| Forex e ouro ao vivo no gráfico | **Parcial**: o script com confluência e linhas compila no TradingView, em simulado, mas some ao recarregar a página enquanto não for salvo na conta. Sem operação verificada ainda |
| Técnicas testadas: Price Action, estrutura, Fibonacci, Wyckoff, Order Blocks, FVG, varreduras, Volume Profile, indicadores, candles, multi-timeframe | **Funciona** como ferramentas medidas. A maioria não mostrou vantagem |
| Confluência com pesos aprendidos | **Funciona** em simulado, sem aprovação |
| Seguir traders | **Código preservado e testado**. Não roda como serviço no servidor |
| RAG e biblioteca com fontes externas | **Parcial**: a busca funciona, mas ainda não alimenta as decisões |
| LLM lendo notícias, com contexto assíncrono | **Parcial**: roda em segundo plano, e o contexto só vai para o diário. Respostas sobre técnicas falham na conferência |
| Regimes e previsão de volatilidade | **Parcial**: medidos no laboratório, ainda fora da decisão |
| Harmonic Patterns e Elliott Wave | **Não implementado** como ferramenta testável |
| Order Flow como atributo | **Não implementado**: os dados são coletados, mas não usados nos modelos |
| Solana/Jupiter e DEXs com modelos próprios; dados on-chain | **Não implementado** |
| Futuros, como operação | **Não implementado**. Hoje só leitura de dados |
| Spot real na Binance e real em Solana | **Não ligado** |
| Operar a Quotex por API ou tela | **Não implementado**. Etapa futura |
| X/Twitter e Trending Topics | **Código pronto, desligado**: sem credencial e sem orçamento |
| Correlacionar eventos externos com preços (geopolítica, eleições) | **Não implementado**: só o estudo de reação a eventos macro |
| LLM formulando hipóteses, analisando operações e propondo melhorias | **Não implementado** |
| LangGraph | **Não implementado** |
| Knowledge Vault navegável no Obsidian, com histórico, natureza das notas e backup | **Funciona**: gerado do laboratório e indexado no RAG. A LLM ainda não propõe hipóteses sozinha |
| Deep Learning | **Não implementado** |
| Ciclo automático de evolução, com comparação de versões | **Não implementado**: hoje o treino é disparado à mão |

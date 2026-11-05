# Gestão de risco

**Situação:** proposta aguardando aprovação.

## Princípios

1. **Determinístico e independente:** código puro em `risco/`, sem LLM, sem rede para decidir e testável por completo.
2. **Caminho único:** só a `Ordem` assinada pelo Risk Engine chega ao executor. Isso é imposto pelo tipo de dado e por teste automático.
3. **Na dúvida, não abre:** erro, dado velho ou limite vazio significam recusa.
4. **Abrir e sair são diferentes:** limites bloqueiam entradas; saídas continuam, conforme a visão.
5. **Valores em Configurações**, nunca no código. Sem valor, sem modo real.

## Limites

Cada limite existe por estratégia, por mercado e no global, valendo o mais restritivo.

| Controle | Regra | Ação | Hoje |
|---|---|---|---|
| Perda diária | Patrimônio do dia, na virada de Brasília | Sem entradas até a meia-noite | Existe, mas está **vazio** |
| Meta diária | Atingida | Sem entradas até a meia-noite | Existe, mas está vazia |
| Exposição | Total e por ativo | Recusa ou reduz | Não existe |
| Tamanho de posição | Máximo em % e valor | Reduz | Parcial |
| Operações simultâneas | Por mercado e no total | Recusa | Não existe |
| Drawdown | Sobre o pico | Para entradas até revisão humana | Não existe |
| Ordens duplicadas | Chave única | Recusa | Parcial |
| Dados velhos | Idade máxima por fonte | Bloqueia entradas | Não existe |
| Slippage | Cotação comparada ao limite | Recusa | Só no legado |
| Liquidez mínima | Tamanho contra liquidez | Recusa | Parcial |
| Frequência | Ordens por minuto e por dia | Recusa | Não existe |
| Correlação | Ativos altamente correlacionados contam juntos | Reduz | Não existe |
| Circuit breaker | N falhas seguidas ou anomalia | Pausa automática | Só no legado |
| Kill switch | Comando humano ou automático | Ver abaixo | Não existe |
| Capital | Máximo alocado por mercado | Recusa | Não existe |

### Regras específicas por modalidade

| Modalidade | Regras próprias |
|---|---|
| Solana | Risco de perda total: tamanho menor; bloqueio de token com alerta de risco; liquidez mínima; reserva de SOL para taxas; concentração de holders |
| Binance Spot | Ordem com preço limite; respeito aos filtros do par |
| Opção digital (só sinal) | Sem recomendar valor; **proibida qualquer recuperação por aumento de aposta**, como martingale; limite de sinais por dia |
| Futuros | Bloqueado |

## Kill switch e circuit breaker

| | Circuit breaker | Kill switch global |
|---|---|---|
| Disparo | Automático: falhas, dados velhos, divergência de saldo, drawdown | Comando no Telegram do dono, na tela ou arquivo local na A1 |
| Efeito | Pausa entradas do módulo | Bloqueia **todas** as ordens novas em todos os mercados |
| Posições | Continuam com saídas normais | O dono escolhe no comando: manter ou encerrar tudo |
| Retomada | Automática só depois de condição limpa, ou manual | **Sempre manual** |

O kill switch precisa funcionar mesmo sem o site, por isso é verificado também em arquivo local. O estado persiste depois de reinícios.

## Riscos operacionais

| Risco | Situação | Defesa |
|---|---|---|
| Configurações alteradas por terceiros | Autenticação a reforçar | Autenticação real; mudanças com histórico; modo real não aceita afrouxar limites sem confirmação |
| Máquina retomada ou perdida | A1 sem backup | Backup; reconciliação; aviso se o robô parar |
| Robô parado com posição aberta | Possível | Verificação externa de atividade, com aviso; ordens de proteção onde houver |
| Dois robôs ao mesmo tempo | Risco na migração do Mac | Trava de instância no banco, com um único detentor |
| Limite de API | Possível | Fila e orçamento |
| Crédito do provedor | Pode acabar | Aviso antes e parada de entradas dependentes |
| Injeção por notícia | Conteúdo externo | LLM sem ferramenta de ordem |
| Vazamento de chave | Sempre | Chave restrita, carteira dedicada |
| Relógio errado | Possível | NTP; recusa se houver desvio além do limite |

## Testes obrigatórios

- Cada limite: teste no valor, abaixo e acima.
- Testes de propriedade: nenhuma sequência de intenções ultrapassa os limites.
- Teste arquitetural: só `risco/` cria a aprovação exigida por `execucao/`.
- Falhas: banco fora, dados atrasados, relógio errado, retorno inválido do LLM.
- Simulação de crises: repetição de dias extremos e de falta total de dados.

## Antes do capital real

- [ ] Autenticação de Configurações resolvida
- [ ] Todos os limites preenchidos
- [ ] Backup restaurado com sucesso
- [ ] Kill switch testado
- [ ] Reconciliação testada
- [ ] Estratégia em nível 4
- [ ] Aprovação explícita do dono

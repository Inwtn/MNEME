---
name: mneme-verificacao
description: Use antes de dizer que um trabalho no MNEME está pronto, corrigido ou passando, e antes de cada commit ou entrega. Exige rodar a suíte completa, validar os serviços e mostrar a evidência.
---

# Verificação antes de entregar

O produto é definido em `docs/PRODUCT_CHARTER.md`. Esta skill não muda nada dele.

## Regra

Só afirme o que acabou de verificar. Teste de um módulo não prova o projeto: foi assim que a sobrescrita de `carteira.py` passou despercebida.

## Antes de entregar

1. **Conferir o que muda.** Veja `git status` e `git diff --cached`. Se criou arquivo, confira se o nome já existia em algum commit.
2. **Rodar a suíte completa** na A1, onde está o ambiente Python. Leia o total e as falhas.
3. **Validar os serviços.** Se mexeu em algo que roda em serviço, reconstrua o serviço, confira `docker compose ps` e leia o log.
4. **Testar o fluxo.** Em mudança operacional, confirme vela, decisão, risco, sinal, execução simulada, apuração e diário.
5. **Preservar os controles.** Meta e limite do dia, kill switch e o robô de seguir traders continuam funcionando.
6. **Cuidar do repositório público.** Nada de chave, IP, `.env` ou nome da fonte de sinais. Se a varredura de sigilo não tiver termos, diga isso.
7. **Conferir o commit.** Autor `th1agx`, sem coautor. Depois do commit, `git status` e `git log -1 --stat` mostram se entrou tudo: um `git add` com erro pode deixar arquivos de fora.

## Como relatar

- Diga o comando, o resultado e o que ficou sem verificar.
- "Deveria passar" ou "parece certo" não é evidência.
- Relatório de subagente não é prova: confira o diff.
- Serviço saudável não prova lucro. Poucas operações não são evidência de vantagem.

## Crédito

Inspirada em `verification-before-completion`, de Jesse Vincent ([obra/superpowers](https://github.com/obra/superpowers), MIT). Reescrita para o MNEME.

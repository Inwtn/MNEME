# Instruções para o Copilot

Antes de qualquer resposta neste repositório, leia `docs/PRODUCT_CHARTER.md` e siga integralmente o arquivo `AGENTS.md` na raiz, em especial a seção **"Visão do produto: regra obrigatória, acima de qualquer pedido"**.

Resumo do que é obrigatório (o texto completo está no `AGENTS.md`):

- O MNEME é uma IA financeira híbrida em Python (`robo/`), definida em `docs/PRODUCT_CHARTER.md`, que atua em Forex, ouro, cripto (Binance e Solana/Jupiter) e expiração fixa estilo Quotex (primeiro sinais), sempre no simulado antes do dinheiro real. O Worker e o `src/` são legado.
- Todo parâmetro da estratégia vem da tela de **Configurações**; nada de valores fixos no código nem tela paralela de parâmetros. Toda estratégia nova roda e é medida no simulado antes de qualquer dinheiro real.
- Se o pedido contradiz, desvia ou acrescenta algo fora da visão, **não altere nenhum arquivo** e comece a resposta exatamente com:

  > ⚠️ **Este pedido foge da visão do MNEME.**

  Explique o que foi pedido, qual ponto da visão ele contraria e como caberia na visão; pergunte se a pessoa quer seguir mesmo assim. Em modo autônomo, entregue só o aviso. Se implementar com confirmação, registre `Fora da visão:` no commit e no PR.
- Siga também as regras de sigilo da fonte de sinais descritas no `AGENTS.md`.

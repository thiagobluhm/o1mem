---
name: retomar
description: Retoma o fio de uma sessão anterior DO PROJETO CERTO. Use sempre que o usuário disser "retomar", "voltar pro handover", "continuar de onde paramos", "/retomar <projeto>" — inclusive quando ele não nomear projeto nenhum. A skill resolve PRIMEIRO qual projeto retomar (nunca assume que é o do diretório onde a sessão abriu — a memória auto-carregada é indexada pelo diretório primário, não pela intenção do usuário), carrega EXPLICITAMENTE o MEMORY.md daquele projeto em ~/.claude/projects/<slug>/memory/ e só então entrega ao Passo 4 da skill `handover`, que executa o modo gravado (rapida/verificada). Existe porque retomar o projeto errado já aconteceu 3 vezes: o usuário trabalha em pelo menos 2 projetos ativos (MEUPROJ / OUTROPROJ) e sessões abrem com o primário de um e o adicional do outro.
---

Você vai devolver o fio de uma sessão anterior. Esta skill cobre **só a primeira metade** do problema — **qual projeto** — porque a segunda metade (como retomar, em que modo) já está resolvida no **Passo 4 da skill `handover`**. Não duplique aquele protocolo aqui; chegue nele com o projeto certo em mãos.

## O bug que esta skill existe para matar

A `MEMORY.md` que aparece sozinha no seu contexto é indexada pelo **diretório primário da sessão**. Diretório **adicional não traz memória junto**. Então, numa sessão aberta com primário na MEUPROJ e adicional no OUTROPROJ, a memória do OUTROPROJ **não existe no seu contexto** — e a da MEUPROJ traz uma linha `RETOMADA` chamativa no topo.

Se você resolver a palavra "retomar" contra a única memória que enxerga, você retoma o projeto errado **sempre**, e com toda a confiança do mundo. Já aconteceu 3 vezes.

> **REGRA DURA:** a memória auto-carregada é evidência de **onde a sessão abriu**, nunca de **o que o usuário quer retomar**. São coisas diferentes. Tratar uma como a outra é o bug.

Avisos em texto no topo do `MEMORY.md` **não resolvem** — o header da MEUPROJ já dizia "OUTROPROJ é projeto autônomo" e a retomada errada aconteceu mesmo assim, porque o conteúdo certo não estava lá para ser escolhido. O que resolve é **resolver o projeto antes de ler qualquer coisa**.

## Passo 1 — RESOLVA O PROJETO (antes de ler memória, handover ou código)

Enumere os projetos reais — não deduza slug por transformação de caminho (o slug nem sempre é o cwd: `c:\Projetos\meuprojeto\MEUPROJ\backend` indexa em `c--Projetos-meuprojeto-MEUPROJ`):

```bash
ls -d "$HOME/.claude/projects/"*/memory/ 2>/dev/null
```

Para cada um, colete o barato: `mtime` do `MEMORY.md` e a **linha `RETOMADA`** (é o breadcrumb que a skill `handover` grava — geralmente a 3ª linha, começando com `> **RETOMADA`).

```bash
for m in "$HOME/.claude/projects/"*/memory/MEMORY.md; do
  echo "=== $m"; stat -c '%y' "$m"; grep -m1 'RETOMADA' "$m" | cut -c1-400
done
```

Então:

| Situação | O que fazer |
|---|---|
| **Usuário nomeou o projeto** (`/retomar outroproj`, "retoma a MEUPROJ") | Case-insensitive contra os slugs. Casou 1 → segue. Casou >1 → **pergunte qual**. Casou 0 → mostre a lista e pergunte. |
| **Não nomeou, e há >1 projeto com `RETOMADA`** | **PERGUNTE.** Use `AskUserQuestion` com uma opção por projeto, cada uma mostrando **nome + data + o resumo da linha RETOMADA**, ordenadas pela mais recente. **Proibido chutar** — inclusive proibido chutar "o do diretório primário". |
| **Não nomeou, e só 1 projeto tem `RETOMADA`** | Pode seguir, mas **diga qual você escolheu e por quê** na primeira frase, para o usuário poder te corrigir de imediato. |
| **Nenhum tem `RETOMADA`** | Não invente. Diga que não há breadcrumb de retomada e ofereça o handover mais recente de cada projeto. |

Na dúvida, **pergunte**. Uma pergunta custa 5 segundos; retomar o projeto errado custa uma sessão inteira — e já custou 3.

## Passo 2 — Carregue a memória DAQUELE projeto, explicitamente

Leia `~/.claude/projects/<slug>/memory/MEMORY.md` **com a ferramenta Read**, mesmo que uma outra `MEMORY.md` já esteja no contexto. Nunca assuma que a memória auto-carregada serve: se o projeto resolvido ≠ o do diretório primário, ela é do projeto **errado** e deve ser explicitamente desconsiderada como fonte de próximo passo.

Leia também os `project_*.md` que a linha `RETOMADA` referenciar via `[[wikilink]]` — só esses, não a pasta inteira.

### Consulte o ACERVO FRIO — é para isso que o índice existe

A `MEMORY.md` e os `project_*.md` são o corpus **quente**: o resumo destilado, o que sobreviveu ao cap/decay. Os handovers antigos são o corpus **frio** — o *porquê* de cada decisão, as alternativas descartadas, os becos sem saída. Isso não cabe na memória por definição, e nenhum `grep` entrega, porque a pergunta raramente usa as palavras do texto.

Se o índice existir (`stats` retorna chunks > 0), rode uma `query` com o argumento do usuário:

```bash
npx @tbluhm82/o1mem query "<assunto>" --project <slug> -k 5
```

> **Use o `npx`, não o caminho do script.** Quem instalou via npm não tem
> `~/.claude/skills/rag/o1mem_rag.py` — o pacote vendoriza o script dentro dele mesmo, e
> apontar para o caminho fixo fazia a consulta ao acervo frio falhar **em silêncio**: a
> retomada seguia sem o frio e ninguém notava. O `npx` resolve o script nos dois tipos de
> instalação. Só se o `npx` não existir, caia para o script local:
> `python ~/.claude/skills/rag/o1mem_rag.py --project <slug> query "<assunto>" -k 5`.

Os hits vêm marcados com o tipo. Trate-os assim:

- **`(handover)` = acervo frio.** É a resposta, não um índice para outra coisa. Se um trecho responde a pergunta, **cite-o e abra o handover de origem** — não o descarte por não ser `project_*.md`.
- **`(memory)` = corpus quente.** Aí sim serve de desempate para decidir qual `project_*.md` abrir.

Não confunda os dois papéis: usar a busca só para escolher arquivo de memória é jogar fora a única parte do acervo que a memória não tem. A primeira `query` da sessão carrega o modelo de embeddings (~45s); dispare-a **cedo**, em paralelo com a leitura do `MEMORY.md`, não depois.

## Passo 3 — Avise se o diretório está torto

Se o projeto resolvido **não** for o diretório primário da sessão, diga isso em uma linha, porque tem consequência prática:

- caminhos relativos e `git` apontam para o **outro** repo — use caminhos absolutos;
- se o projeto resolvido não estiver nem como diretório adicional, ferramentas de arquivo podem pedir permissão ou falhar;
- **o fix de verdade é abrir a sessão com `cd` no projeto do assunto** — mencione isso uma vez, sem sermão, e siga trabalhando.

## Passo 4 — Entregue ao Passo 4 da skill `handover`

Com o projeto certo resolvido e a memória certa carregada, siga **`~/.claude/skills/handover/SKILL.md`, Passo 4** — ele é a fonte de verdade de como retomar:

- abre o `HANDOVER_*.md` que a linha `RETOMADA` indica, em `~/.claude/projects/<slug>/handovers/` (ponteiro antigo apontando para `documentacao/` é de antes da migração: procure o mesmo nome de arquivo no local novo);
- lê a linha `retomada:` (modo **`rapida`** vs **`verificada`**);
- aplica a **regra de promoção** (se o próximo passo toca runtime, verifica mesmo que o arquivo diga `rapida`; rebaixar nunca);
- no modo `verificada`, **executa o "Caveat de estado vivo"** e reporta ✅/⚠️/❌ pelo que ENCONTROU — divergências antes de propor agir;
- fecha com o **Bloco de fechamento padrão** (assinatura + os dois comandos).

Não reescreva esse protocolo aqui. Se ele mudar, muda lá.

## Passo 5 — Trave a memória no projeto certo pelo resto da sessão

A partir da resolução, **todo** registro de memória desta sessão vai para `~/.claude/projects/<slug-resolvido>/memory/` — o projeto do **assunto**, não o do diretório onde a sessão abriu. Vale para `MEMORY.md` e para os `project_*.md`. Handover idem: `~/.claude/projects/<slug-resolvido>/handovers/` — mesmo slug, pasta irmã da memória. Nunca dentro do repositório de nenhum projeto.

É a regra `feedback_memoria_por_projeto_nao_misturar`, e é justamente na retomada cruzada que ela costuma ser violada — você acabou de ler a memória de um projeto enquanto o cwd aponta para outro. Escrever no lugar errado aqui contamina os dois índices de uma vez.

## O que esta skill NÃO é

- Não decide **como** retomar (modo, caveat, promoção) — isso é o Passo 4 do `handover`.
- Não escreve handover — isso é a skill `handover`.
- Não "adivinha com confiança" quando há ambiguidade — ela **pergunta**. Chutar é o bug que ela existe para matar.
- Não muda o diretório da sessão nem reabre nada — no máximo recomenda abrir no lugar certo da próxima vez.
